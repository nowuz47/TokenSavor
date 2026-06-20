use tauri::image::Image;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, WindowEvent};
use tauri_plugin_clipboard_manager::ClipboardExt;
use tauri_plugin_global_shortcut::ShortcutState;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

use std::io::{Read, Write};
use std::net::TcpStream;
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

#[cfg(windows)]
use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
    SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYEVENTF_KEYUP, VK_A, VK_C, VK_CONTROL,
    VK_V,
};

struct BackendState {
    child: Mutex<Option<CommandChild>>,
}

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn hide_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
}

fn health_check_backend() -> bool {
    let Ok(mut stream) = TcpStream::connect_timeout(
        &"127.0.0.1:8750"
            .parse()
            .expect("valid local socket address"),
        Duration::from_millis(350),
    ) else {
        return false;
    };

    let _ = stream.set_read_timeout(Some(Duration::from_millis(700)));
    let request = b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
    if stream.write_all(request).is_err() {
        return false;
    }

    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return false;
    }
    response.contains("\"status\":\"ok\"") || response.contains("\"status\": \"ok\"")
}

fn start_backend_sidecar(app: &tauri::App) {
    if health_check_backend() {
        return;
    }

    let state = app.state::<BackendState>();
    match app.shell().sidecar("scrooge-backend") {
        Ok(command) => match command.spawn() {
            Ok((mut rx, child)) => {
                *state.child.lock().expect("backend child mutex poisoned") = Some(child);
                thread::spawn(move || {
                    while let Some(event) = rx.blocking_recv() {
                        let _ = event;
                    }
                });
            }
            Err(error) => {
                eprintln!("Failed to spawn scrooge-backend sidecar: {error}");
            }
        },
        Err(error) => {
            eprintln!("Failed to create scrooge-backend sidecar command: {error}");
        }
    }
}

fn optimize_active_field_via_backend(app: AppHandle) {
    thread::spawn(move || {
        thread::sleep(Duration::from_millis(350));
        let previous_clipboard = app.clipboard().read_text().ok();
        send_ctrl_key('A');
        thread::sleep(Duration::from_millis(80));
        send_ctrl_key('C');
        thread::sleep(Duration::from_millis(220));

        let Ok(text) = app.clipboard().read_text() else {
            emit_hotkey_result(&app, "failed", 0, "");
            return;
        };
        if text.trim().is_empty() {
            if let Some(previous) = previous_clipboard {
                let _ = app.clipboard().write_text(previous);
            }
            emit_hotkey_result(&app, "empty", 0, "");
            return;
        }

        let body = serde_json::json!({
            "prompt": text,
            "provider": "openai",
            "model": "gpt-5.4-mini",
            "task_type": null,
            "expected_output_tokens": 1000,
            "capture_source": "hotkey"
        });
        let Some(response) = post_json("/api/optimize", &body) else {
            let _ = app.clipboard().write_text(text);
            send_ctrl_key('V');
            emit_hotkey_result(&app, "failed", 0, "");
            return;
        };
        let request_id = response
            .get("request_id")
            .and_then(|value| value.as_str())
            .unwrap_or_default()
            .to_string();
        let saved_tokens = response
            .get("saved_tokens")
            .and_then(|value| value.as_i64())
            .unwrap_or(0);

        if saved_tokens <= 0 {
            if !request_id.is_empty() {
                let _ = post_json(
                    &format!("/api/approvals/{request_id}/approve"),
                    &serde_json::json!({ "approved": false, "notes": "no_savings" }),
                );
            }
            let _ = app.clipboard().write_text(text);
            send_ctrl_key('V');
            emit_hotkey_result(&app, "no_savings", 0, &request_id);
            return;
        }

        let Some(optimized_prompt) = response
            .get("optimized_prompt")
            .and_then(|value| value.as_str())
        else {
            let _ = app.clipboard().write_text(text);
            send_ctrl_key('V');
            emit_hotkey_result(&app, "failed", 0, &request_id);
            return;
        };

        if app.clipboard().write_text(optimized_prompt).is_ok() {
            thread::sleep(Duration::from_millis(80));
            send_ctrl_key('V');
            if !request_id.is_empty() {
                let _ = post_json(
                    &format!("/api/approvals/{request_id}/approve"),
                    &serde_json::json!({ "approved": true }),
                );
            }
            emit_hotkey_result(&app, "optimized", saved_tokens, &request_id);
        } else {
            emit_hotkey_result(&app, "failed", 0, &request_id);
        }
    });
}

fn emit_hotkey_result(app: &AppHandle, status: &str, saved_tokens: i64, request_id: &str) {
    let _ = app.emit(
        "scrooge-hotkey-result",
        serde_json::json!({
            "status": status,
            "saved_tokens": saved_tokens,
            "request_id": request_id
        }),
    );
}

#[cfg(windows)]
fn send_ctrl_key(key: char) {
    let virtual_key = match key {
        'A' => VK_A,
        'C' => VK_C,
        'V' => VK_V,
        _ => return,
    };
    let mut inputs = [
        keyboard_input(VK_CONTROL, false),
        keyboard_input(virtual_key, false),
        keyboard_input(virtual_key, true),
        keyboard_input(VK_CONTROL, true),
    ];
    unsafe {
        let _ = SendInput(
            inputs.len() as u32,
            inputs.as_mut_ptr(),
            std::mem::size_of::<INPUT>() as i32,
        );
    }
}

#[cfg(not(windows))]
fn send_ctrl_key(_key: char) {}

#[cfg(windows)]
fn keyboard_input(vk: u16, key_up: bool) -> INPUT {
    INPUT {
        r#type: INPUT_KEYBOARD,
        Anonymous: INPUT_0 {
            ki: KEYBDINPUT {
                wVk: vk,
                wScan: 0,
                dwFlags: if key_up { KEYEVENTF_KEYUP } else { 0 },
                time: 0,
                dwExtraInfo: 0,
            },
        },
    }
}

fn post_json(path: &str, body: &serde_json::Value) -> Option<serde_json::Value> {
    let payload = serde_json::to_string(body).ok()?;
    let mut stream = TcpStream::connect_timeout(
        &"127.0.0.1:8750"
            .parse()
            .expect("valid local socket address"),
        Duration::from_millis(700),
    )
    .ok()?;
    let _ = stream.set_read_timeout(Some(Duration::from_secs(5)));
    let request = format!(
        "POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{payload}",
        payload.len()
    );
    stream.write_all(request.as_bytes()).ok()?;

    let mut response = String::new();
    stream.read_to_string(&mut response).ok()?;
    let (_, body) = response.split_once("\r\n\r\n")?;
    serde_json::from_str(body).ok()
}

fn stop_backend_sidecar(app: &AppHandle) {
    let state = app.state::<BackendState>();
    let child = {
        state
            .child
            .lock()
            .expect("backend child mutex poisoned")
            .take()
    };
    if let Some(child) = child {
        let _ = child.kill();
    }
}

fn force_quit(app: &AppHandle) -> ! {
    stop_backend_sidecar(app);
    std::process::exit(0);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let shortcut_plugin =
        match tauri_plugin_global_shortcut::Builder::new().with_shortcuts(["ctrl+alt+s"]) {
            Ok(builder) => builder
                .with_handler(|app, _shortcut, event| {
                    if event.state == ShortcutState::Pressed {
                        optimize_active_field_via_backend(app.clone());
                    }
                })
                .build(),
            Err(_) => tauri_plugin_global_shortcut::Builder::new().build(),
        };

    tauri::Builder::default()
        .manage(BackendState {
            child: Mutex::new(None),
        })
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(shortcut_plugin)
        .plugin(tauri_plugin_shell::init())
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .setup(|app| {
            start_backend_sidecar(app);

            let app_icon = Image::from_bytes(include_bytes!("../icons/icon.png"))?;
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_icon(app_icon.clone());
            }

            let show = MenuItem::with_id(app, "show", "Show Scrooge", true, None::<&str>)?;
            let hide = MenuItem::with_id(app, "hide", "Close Window", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit Scrooge", true, None::<&str>)?;
            let force_quit_item =
                MenuItem::with_id(app, "force_quit", "Force Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &hide, &quit, &force_quit_item])?;
            let app_handle = app.handle().clone();

            TrayIconBuilder::new()
                .icon(app_icon)
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => show_main_window(app),
                    "hide" => hide_main_window(app),
                    "quit" => {
                        stop_backend_sidecar(app);
                        app.exit(0);
                    }
                    "force_quit" => force_quit(app),
                    _ => {}
                })
                .on_tray_icon_event(move |_tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_main_window(&app_handle);
                    }
                })
                .build(app)?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Scrooge");
}
