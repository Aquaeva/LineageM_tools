import threading
import time
import win32api
import win32con
import win32gui

class Overlay:
    """
    Overlay 類別 - 在指定目標視窗上方顯示半透明浮動訊息

    功能:
    1. 顯示自訂文字訊息，支援多行換行。
    2. 可設定字型大小、文字顏色、背景顏色、透明度。
    3. 支援自動隱藏（秒數可設定）。
    4. 自動追蹤目標視窗位置，浮動視窗始終保持在目標視窗上方。

    參數:
    target_title: str        目標視窗標題
    width: int               Overlay 視窗寬度 (像素)，預設 300
    alpha: float             透明度 (0~1)，預設 0.5
    font_color: tuple        文字顏色 RGB，預設 (255,0,0)
    bg_color: tuple          背景顏色 RGB，預設 (0,0,0)
    font_size: int           文字字型大小 (像素)，預設 24
    """

    def __init__(self, target_title, width=200, alpha=0.5,
                 font_color=(255, 0, 0), bg_color=(0, 0, 0), font_size=24,
                 offset_x=-200, offset_y=60):
        self.target_title = target_title
        self.width = width
        self.height = 25
        self.alpha = alpha
        self.font_color = font_color
        self.bg_color = bg_color
        self.font_size = font_size
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.text = ""
        self.visible = False
        self.lock = threading.Lock()
        self.hide_timestamp = None

        self.hInstance = win32api.GetModuleHandle(None)

        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self.wnd_proc
        wc.lpszClassName = f"OverlayWindow_{time.time()}"
        wc.hInstance = self.hInstance
        wc.hCursor = win32api.LoadCursor(0, win32con.IDC_ARROW)
        win32gui.RegisterClass(wc)

        self.hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_LAYERED |
            win32con.WS_EX_TOPMOST |
            win32con.WS_EX_TOOLWINDOW |
            win32con.WS_EX_TRANSPARENT |
            win32con.WS_EX_NOACTIVATE,
            wc.lpszClassName,
            "",
            win32con.WS_POPUP,
            0, 0, self.width, self.height,
            None, None, self.hInstance, None
        )
        win32gui.SetLayeredWindowAttributes(
            self.hwnd, 0, int(255 * self.alpha), win32con.LWA_ALPHA
        )

        threading.Thread(target=self.follow_target, daemon=True).start()

    def wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_PAINT:
            hdc, ps = win32gui.BeginPaint(hwnd)
            rect = win32gui.GetClientRect(hwnd)

            brush = win32gui.CreateSolidBrush(win32api.RGB(*self.bg_color))
            win32gui.FillRect(hdc, rect, brush)
            win32gui.DeleteObject(brush)

            lf = win32gui.LOGFONT()
            lf.lfHeight = -self.font_size
            lf.lfWeight = win32con.FW_BOLD
            lf.lfFaceName = "Microsoft YaHei"
            font = win32gui.CreateFontIndirect(lf)
            old_font = win32gui.SelectObject(hdc, font)

            win32gui.SetTextColor(hdc, win32api.RGB(*self.font_color))
            win32gui.SetBkMode(hdc, win32con.TRANSPARENT)

            with self.lock:
                display_text = self.text

            # 多行文字
            win32gui.DrawText(
                hdc,
                display_text,
                -1,
                rect,
                win32con.DT_LEFT | win32con.DT_WORDBREAK | win32con.DT_VCENTER
            )

            win32gui.SelectObject(hdc, old_font)
            win32gui.DeleteObject(font)
            win32gui.EndPaint(hwnd, ps)
            return 0
        elif msg == win32con.WM_CLOSE:
            win32gui.DestroyWindow(hwnd)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def show(self):
        if not self.visible:
            win32gui.ShowWindow(self.hwnd, win32con.SW_SHOWNOACTIVATE)
            self.visible = True

    def hide(self):
        if self.visible:
            win32gui.ShowWindow(self.hwnd, win32con.SW_HIDE)
            self.visible = False

    def set_width(self, new_width):
        if new_width == self.width:
            return
        
        old_width = self.width
        self.width = new_width
        print(f"Overlay 寬度調整: {old_width}px → {new_width}px")
        
        win32gui.SetWindowPos(
            self.hwnd, None, 0, 0, self.width, self.height,
            win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
        )
        win32gui.InvalidateRect(self.hwnd, None, True)


    def update_text(self, text="", hide_after=None, font_color=None, bg_color=None, alpha=None, font_size=None):
        with self.lock:
            self.text = text
            if font_color:
                self.font_color = font_color
            if bg_color:
                self.bg_color = bg_color
            if font_size is not None:
                self.font_size = font_size
            if alpha is not None:
                self.alpha = alpha
                win32gui.SetLayeredWindowAttributes(
                    self.hwnd, 0, int(255 * self.alpha), win32con.LWA_ALPHA
                )

        lines = text.count("\n") + 1
        self.height = max(25, lines * (self.font_size + 7))
        win32gui.SetWindowPos(
            self.hwnd, None, 0, 0, self.width, self.height,
            win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
        )

        if not self.visible:
            self.show()
        else:
            win32gui.InvalidateRect(self.hwnd, None, True)

        if hide_after and hide_after > 0:
            self.hide_timestamp = time.time() + hide_after
        else:
            self.hide_timestamp = None

    def follow_target(self):
        while True:
            hwnd_game = win32gui.FindWindow(None, self.target_title)
            if hwnd_game and self.visible:
                l, t, r, b = win32gui.GetWindowRect(hwnd_game)
                w_game = r - l
                h_game = b - t

                # 視窗中心
                center_x = l + w_game // 2
                center_y = t + h_game // 2

                # 使用動態偏移
                x = center_x + self.offset_x - self.width // 2
                y = center_y + self.offset_y - self.height // 2  # 垂直置中

                win32gui.SetWindowPos(
                    self.hwnd,
                    win32con.HWND_TOPMOST,
                    x, y, self.width, self.height,
                    win32con.SWP_NOACTIVATE
                )

            # 自動隱藏檢查
            if self.hide_timestamp and time.time() >= self.hide_timestamp:
                self.hide()
                self.hide_timestamp = None

            time.sleep(0.02)
