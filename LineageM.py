import frida
import sys

# 目標進程的包名

package_name = "天堂M助手+"
#// 重要說明(不可移除) C0391 Class Name：SocketUtils.m1134(6444, new C0323(211)); 在GameHelper 找211指令 然後進入C0323就可以取的 -"ቌ.ᣇ.ᶬ.ಞ.㚽.Ố"
#// 重要說明(不可移除) MoveTo Classname：在GameHelper 找402指令 就可以取的"混淆變數" -䄼
#// 重要說明(不可移除) UseItem Method Name：在GameHelper 找404指令 就可以取的"混淆變數" -䇪
#// 重要說明(不可移除) SocketUtils Method：路徑 com.lineagem.botv3.util 取的"混淆變數" -ᶬ
# [已棄用] 請改用 RPC 模式 (create_main_monitor_script) 以避免記憶體洩漏
# def get_script_code(code, c0391_class_name, socket_utils_method):
#     """根據指令代碼生成Frida腳本，用於獲取資訊。"""
#     return rf"""
#     Java.perform(function () {{ 
#         try {{ 
#             var SocketUtils = Java.use("com.lineagem.botv3.util.SocketUtils");
#             var C0391 = Java.use("{c0391_class_name}");
#             var C0391_instance = C0391.$new({code});
#             var result = SocketUtils["{socket_utils_method}"](6444, C0391_instance);
#             send(result); // 使用 send 將結果傳回
#         }} catch (e) {{ 
#             send('[❌] get_script_code 調用失敗: ' + e);
#         }}
#     }}); 
#     """

# [已棄用] 請改用 RPC 模式 (create_main_monitor_script) 以避免記憶體洩漏
# def get_use_item_script(item_key, use_item_method_name):
#     """生成使用指定 itemKey 物品的Frida腳本。"""
#     return f"""
#     Java.perform(function () {{
#         try {{
#             var GameHelper = Java.use("com.lineagem.botv3.plugin.GameHelper");
#             var Long = Java.use("java.lang.Long");
#             var itemKeyLong = Long.parseLong('{item_key}');
#             var useResult = GameHelper["{use_item_method_name}"](itemKeyLong);
#             send('[✔] GameHelper.{use_item_method_name} 返回值: ' + useResult);
#         }} catch (e) {{
#             send('[❌] get_use_item_script 調用失敗: ' + e.message);
#         }}
#     }}); 
#     """

def create_main_monitor_script(session, c0391_class_name, socket_utils_method, use_item_method_name, auto_method_name, skill_use_method_name, target_method_name, attack_pickup_method_name, moveto_classname):
    """創建一個整合的、包含多個 RPC 功能的監控腳本。"""
    script_code = f"""
        var SocketUtils, C0391, GameHelper, Long;
        Java.perform(function() {{
            SocketUtils = Java.use("com.lineagem.botv3.util.SocketUtils");
            C0391 = Java.use(eval('"' + "{c0391_class_name}" + '"'));
            GameHelper = Java.use("com.lineagem.botv3.plugin.GameHelper");
            Long = Java.use("java.lang.Long");
        }});

        rpc.exports = {{
            getInfo: function(code) {{
                try {{
                    var instance = C0391.$new(parseInt(code));
                    var result = SocketUtils["{socket_utils_method}"](6444, instance);
                    return result;
                }} catch (e) {{
                    return e.message;
                }}
            }},

            useItem: function(itemKey) {{
                return new Promise(function(resolve, reject) {{
                    send('[RPC] useItem 正在執行，Key: ' + itemKey);
                    try {{
                        var key = Long.parseLong(itemKey.toString());
                        var result = GameHelper["{use_item_method_name}"](key);
                        send('[RPC] GameHelper["{use_item_method_name}"] 回傳: ' + result);
                        resolve(result);
                    }} catch (e) {{
                        send('[RPC] useItem 發生錯誤: ' + e.message);
                        reject(e.message);
                    }}
                }});
            }},

            toggleAuto: function(enable) {{
                return new Promise(function(resolve, reject) {{
                    send('[RPC] toggleAuto 正在執行，enable: ' + enable);
                    try {{
                        var result = GameHelper["{auto_method_name}"](enable);
                        send('[RPC] GameHelper["{auto_method_name}"] 回傳: ' + result);
                        resolve(result);
                    }} catch (e) {{
                        send('[RPC] toggleAuto 發生錯誤: ' + e.message);
                        reject(e.message);
                    }}
                }});
            }},

            useSkill: function(skillId, targetKey) {{
                return new Promise(function(resolve, reject) {{
                    send('[RPC] useSkill 正在執行，skillId: ' + skillId + ', targetKey: ' + targetKey);
                    try {{
                        var key = Long.parseLong(targetKey.toString());
                        var result = GameHelper["{skill_use_method_name}"](skillId, key);
                        send('[RPC] GameHelper["{skill_use_method_name}"] 回傳: ' + result);
                        resolve(result);
                    }} catch (e) {{
                        send('[RPC] useSkill 發生錯誤: ' + e.message);
                        reject(e.message);
                    }}
                }});
            }},

            setTarget: function(objectKey) {{
                return new Promise(function(resolve, reject) {{
                    send('[RPC] setTarget 正在執行，objectKey: ' + objectKey);
                    try {{
                        var key = Long.parseLong(objectKey.toString());
                        var result = GameHelper["{target_method_name}"](key);
                        send('[RPC] GameHelper["{target_method_name}"] 回傳: ' + result);
                        resolve(result);
                    }} catch (e) {{
                        send('[RPC] setTarget 發生錯誤: ' + e.message);
                        reject(e.message);
                    }}
                }});
            }},

            attackPickup: function() {{
                return new Promise(function(resolve, reject) {{
                    send('[RPC] attackPickup 正在執行');
                    try {{
                        var result = GameHelper["{attack_pickup_method_name}"]();
                        send('[RPC] GameHelper["{attack_pickup_method_name}"] 回傳: ' + result);
                        resolve(result);
                    }} catch (e) {{
                        send('[RPC] attackPickup 發生錯誤: ' + e.message);
                        reject(e.message);
                    }}
                }});
            }},

            moveto: function(x, y) {{
                return new Promise(function(resolve, reject) {{
                    // send('[RPC] moveto 正在執行: ' + x + ', ' + y); // Optional logging
                    try {{
                        // 檢查方法是否存在
                        if (typeof GameHelper["{moveto_classname}"] !== 'function') {{
                            send("[Error] GameHelper.{moveto_classname} 不是一個函數！請檢查 Classname 設定。");
                            reject("Method not found");
                            return;
                        }}
                        var result = GameHelper["{moveto_classname}"](x, y);
                        // send('[RPC] GameHelper["{moveto_classname}"] 回傳: ' + result);
                        resolve(result);
                    }} catch (e) {{
                        send('[RPC] moveto 發生錯誤: ' + e.message);
                        reject(e.message);
                    }}
                }});
            }}
        }};
    """
    script = session.create_script(script_code)
    return script

# [已棄用] 請改用 RPC 模式 (create_main_monitor_script) 以避免記憶體洩漏
# # Frida 腳本
# def execute_script(session, input_value, c0391_class_name, socket_utils_method):
#     script_code = get_script_code(input_value, c0391_class_name=c0391_class_name, socket_utils_method=socket_utils_method)
#     script = session.create_script(script_code)
#     return script

# [已棄用] 請改用 RPC 模式 (create_main_monitor_script) 以避免記憶體洩漏
# def moveto(session, x, y, classname):
#     script_code = f"""
#     Java.perform(function () {{
#         try {{
#             var GameHelper = Java.use("com.lineagem.botv3.plugin.GameHelper");
#             // 檢查方法是否存在
#             if (typeof GameHelper["{classname}"] !== 'function') {{
#                 send("[Error] GameHelper.{classname} 不是一個函數！請檢查 Classname 設定。");
#                 return;
#             }}
#             var result = GameHelper["{classname}"]({x}, {y});
#             send("[Called] GameHelper.{classname}({x}, {y})");
#             send("[Returned] " + result);
#         }} catch (e) {{
#             send("[Error] Calling GameHelper.{classname}: " + e.message);
#         }}
#     }}); 
#     """
#     script = session.create_script(script_code)
#     return script

# [已棄用] 請改用 RPC 模式 (create_main_monitor_script) 以避免記憶體洩漏
# def back_to_village_script(session, c0391_class_name, socket_utils_method, use_item_method_name):
#     script_code = rf"""
# Java.perform(function () {{
#     try {{
#         var SocketUtils = Java.use("com.lineagem.botv3.util.SocketUtils");
#         var C0391 = Java.use("{c0391_class_name}");  
#         var inputValue = 211;
# 
#         send("[⚡] 準備調用 SocketUtils.{socket_utils_method}(6444, new C0391(" + inputValue + "))...");
# 
#         var C0391_instance = C0391.$new(inputValue);
#         var result = SocketUtils["{socket_utils_method}"](6444, C0391_instance);
# 
#         var regex = /\{{\".*?\"itemID":239.*?\"itemKey\":(\d+).*?\\}}/;
#         var match = regex.exec(result);
# 
#         if (match && match[1]) {{
#             var itemKey = match[1];
#             send("[✔] 取得 itemKey: " + itemKey);
# 
#             var GameHelper = Java.use("com.lineagem.botv3.plugin.GameHelper");
#             var Long = Java.use("java.lang.Long");
# 
#             send("[⚡] 準備調用 GameHelper.{use_item_method_name} (使用道具)，參數為 itemKey...");
# 
#             var itemKeyLong = Long.parseLong(itemKey);
#             var useResult = GameHelper["{use_item_method_name}"](itemKeyLong);
# 
#             send("[✔] GameHelper.{use_item_method_name} 返回值: " + useResult);
#         }} else {{
#             send("[❌] 未找到 itemID 為 239 的 itemKey。");
#         }}
# 
#     }} catch (e) {{
#         send("[❌] 調用失敗: " + e);
#     }}
# }});  
#     """
#     script = session.create_script(script_code)
#     return script

def get_pid_by_package(package_name, port, logger=print):
    """根據 Android 包名尋找並返回進程 ID 和裝置物件。"""
    try:
        device = None
        manager = frida.get_device_manager()
        device = manager.add_remote_device(f"127.0.0.1:{port}")

        processes = device.enumerate_processes()
        for process in processes:
            if process.name.lower() == package_name.lower():
                logger(f"找到進程 '{package_name}'，PID 為: {process.pid}")
                return process.pid, device

        logger(f"在裝置 {device.name} 上未找到包名為 '{package_name}' 的進程。")
        return None, None
    except Exception as e:
        logger(f"獲取 PID 時發生錯誤: {e}")
        return None, None

def list_frida_devices(logger=print):
    """列出所有已連接的 Frida 裝置的詳細資訊"""
    try:
        devices = frida.enumerate_devices()
        if not devices:
            logger("找不到任何裝置。請確認模擬器或裝置已開啟且已連接。" )
            return

        logger("--- 已連接的 Frida 裝置 ---")
        for device in devices:
            logger(f"  - ID: {device.id}, 名稱: {device.name}, 類型: {device.type}")

    except Exception as e:
        logger(f"列出裝置時發生錯誤: {e}")