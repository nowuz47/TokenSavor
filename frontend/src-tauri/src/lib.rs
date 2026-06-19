use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, WindowEvent};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

use std::io::{Read, Write};
use std::net::TcpStream;
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

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
        println!("Scrooge backend already healthy on 127.0.0.1:8750");
        return;
    }

    let state = app.state::<BackendState>();
    match app.shell().sidecar("scrooge-backend") {
        Ok(command) => match command.spawn() {
            Ok((mut rx, child)) => {
                *state.child.lock().expect("backend child mutex poisoned") = Some(child);
                thread::spawn(move || {
                    while let Some(event) = rx.blocking_recv() {
                        println!("scrooge-backend sidecar: {:?}", event);
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

fn stop_backend_sidecar(app: &AppHandle) {
    let state = app.state::<BackendState>();
    if let Some(child) = state
        .child
        .lock()
        .expect("backend child mutex poisoned")
        .take()
    {
        let _ = child.kill();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendState {
            child: Mutex::new(None),
        })
        .plugin(tauri_plugin_shell::init())
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .setup(|app| {
            start_backend_sidecar(app);

            let show = MenuItem::with_id(app, "show", "Show Scrooge", true, None::<&str>)?;
            let hide = MenuItem::with_id(app, "hide", "Hide to Tray", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &hide, &quit])?;
            let app_handle = app.handle().clone();

            TrayIconBuilder::new()
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => show_main_window(app),
                    "hide" => hide_main_window(app),
                    "quit" => {
                        stop_backend_sidecar(app);
                        app.exit(0);
                    }
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
