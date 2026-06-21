use tauri::image::Image;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, WindowEvent};
use tauri_plugin_clipboard_manager::ClipboardExt;
use tauri_plugin_global_shortcut::ShortcutState;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
    SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYEVENTF_KEYUP, VK_A, VK_C, VK_CONTROL,
    VK_V,
};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct BackendState {
    child: Mutex<Option<CommandChild>>,
}

#[derive(Clone, Copy, Default)]
struct HotkeyAttachmentStats {
    discovered: i64,
    content_available: i64,
    unknown: i64,
    unsupported: i64,
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
    if state
        .child
        .lock()
        .expect("backend child mutex poisoned")
        .is_some()
    {
        return;
    }

    match app.shell().sidecar("scrooge-backend").map(|command| {
        command
            .env("SCROOGE_SIDECAR_STATUS", "managed")
            .env("SCROOGE_HOTKEY_STATUS", "registered")
    }) {
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
        let started = Instant::now();
        let empty_attachment_stats = HotkeyAttachmentStats::default();
        thread::sleep(Duration::from_millis(350));
        let previous_clipboard = app.clipboard().read_text().ok();
        send_ctrl_key('A');
        thread::sleep(Duration::from_millis(80));
        send_ctrl_key('C');
        thread::sleep(Duration::from_millis(220));

        let Ok(text) = app.clipboard().read_text() else {
            emit_hotkey_result(
                &app,
                "failed",
                "clipboard_failed",
                0,
                "",
                Some("clipboard_read_failed"),
                started.elapsed().as_millis(),
                empty_attachment_stats,
            );
            return;
        };
        if text.trim().is_empty() {
            if let Some(previous) = previous_clipboard {
                let _ = app.clipboard().write_text(previous);
            }
            emit_hotkey_result(
                &app,
                "empty",
                "empty_selection",
                0,
                "",
                None,
                started.elapsed().as_millis(),
                empty_attachment_stats,
            );
            return;
        }

        let attachments = discover_hotkey_attachments(&text);
        let attachment_stats = hotkey_attachment_stats(&attachments);
        let body = serde_json::json!({
            "prompt": text,
            "provider": "openai",
            "model": "gpt-5.4-mini",
            "task_type": null,
            "expected_output_tokens": 1000,
            "capture_source": "hotkey",
            "attachments": attachments
        });
        let Some(response) = post_json("/api/optimize", &body) else {
            let _ = app.clipboard().write_text(text);
            send_ctrl_key('V');
            emit_hotkey_result(
                &app,
                "failed",
                "backend_failed",
                0,
                "",
                Some("optimize_request_failed"),
                started.elapsed().as_millis(),
                attachment_stats,
            );
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
            let rejection_note = no_savings_note(&response);
            if !request_id.is_empty() {
                let _ = post_json(
                    &format!("/api/approvals/{request_id}/approve"),
                    &serde_json::json!({ "approved": false, "notes": rejection_note }),
                );
            }
            let _ = app.clipboard().write_text(text);
            send_ctrl_key('V');
            emit_hotkey_result(
                &app,
                "no_savings",
                "no_savings_kept_original",
                0,
                &request_id,
                None,
                started.elapsed().as_millis(),
                attachment_stats,
            );
            return;
        }

        let Some(optimized_prompt) = response
            .get("optimized_prompt")
            .and_then(|value| value.as_str())
        else {
            let _ = app.clipboard().write_text(text);
            send_ctrl_key('V');
            emit_hotkey_result(
                &app,
                "failed",
                "backend_failed",
                0,
                &request_id,
                Some("missing_optimized_prompt"),
                started.elapsed().as_millis(),
                attachment_stats,
            );
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
            emit_hotkey_result(
                &app,
                "optimized",
                "optimized_pasted",
                saved_tokens,
                &request_id,
                None,
                started.elapsed().as_millis(),
                attachment_stats,
            );
        } else {
            emit_hotkey_result(
                &app,
                "failed",
                "clipboard_failed",
                0,
                &request_id,
                Some("optimized_clipboard_write_failed"),
                started.elapsed().as_millis(),
                attachment_stats,
            );
        }
    });
}

fn no_savings_note(response: &serde_json::Value) -> &'static str {
    let original_tokens = response
        .get("original_tokens")
        .and_then(|value| value.get("input_tokens"))
        .and_then(|value| value.as_i64())
        .unwrap_or(0);
    let optimized_tokens = response
        .get("optimized_tokens")
        .and_then(|value| value.get("input_tokens"))
        .and_then(|value| value.as_i64())
        .unwrap_or(0);
    if original_tokens <= 120 {
        "no_savings_short_prompt"
    } else if optimized_tokens >= original_tokens {
        "no_savings_quality_guard"
    } else {
        "no_savings"
    }
}

fn emit_hotkey_result(
    app: &AppHandle,
    status: &str,
    event_status: &str,
    saved_tokens: i64,
    request_id: &str,
    failure_reason: Option<&str>,
    elapsed_ms: u128,
    attachment_stats: HotkeyAttachmentStats,
) {
    let request_id_value = if request_id.is_empty() {
        serde_json::Value::Null
    } else {
        serde_json::json!(request_id)
    };
    let _ = post_json(
        "/api/hotkey/events",
        &serde_json::json!({
            "request_id": request_id_value,
            "status": event_status,
            "failure_reason": failure_reason,
            "saved_tokens": saved_tokens.max(0),
            "elapsed_ms": elapsed_ms,
            "discovered_attachment_count": attachment_stats.discovered,
            "content_available_attachment_count": attachment_stats.content_available,
            "unknown_attachment_count": attachment_stats.unknown,
            "unsupported_attachment_count": attachment_stats.unsupported
        }),
    );
    let _ = app.emit(
        "scrooge-hotkey-result",
        serde_json::json!({
            "status": status,
            "event_status": event_status,
            "saved_tokens": saved_tokens,
            "request_id": request_id,
            "discovered_attachment_count": attachment_stats.discovered,
            "content_available_attachment_count": attachment_stats.content_available,
            "unknown_attachment_count": attachment_stats.unknown,
            "unsupported_attachment_count": attachment_stats.unsupported
        }),
    );
}

fn discover_hotkey_attachments(prompt: &str) -> Vec<serde_json::Value> {
    let mut attachments = Vec::new();
    for path in file_path_candidates(prompt) {
        let name = display_name(&path);
        if attachments.iter().any(|item: &serde_json::Value| {
            item.get("name").and_then(|value| value.as_str()) == Some(name.as_str())
        }) {
            continue;
        }
        attachments.push(attachment_from_path(&path, "workspace_match"));
    }

    for name in codex_ui_attachment_names() {
        if attachments.iter().any(|item: &serde_json::Value| {
            item.get("name").and_then(|value| value.as_str()) == Some(name.as_str())
        }) {
            continue;
        }
        match resolve_attached_file_name(&name, prompt) {
            Some(path) => attachments.push(attachment_from_path(&path, "codex_uia")),
            None => attachments.push(serde_json::json!({
                "name": name,
                "token_status": "unknown",
                "discovery_source": "codex_uia",
                "content_available": false,
                "path_available": false,
                "read_error": "attached_file_path_not_found"
            })),
        }
    }

    if attachments.is_empty() && mentions_attachment(prompt) {
        attachments.push(serde_json::json!({
            "name": "codex-attached-file",
            "token_status": "unknown",
            "discovery_source": "prompt_reference",
            "content_available": false,
            "path_available": false,
            "read_error": "codex_attachment_body_not_exposed"
        }));
    }
    attachments
}

fn hotkey_attachment_stats(attachments: &[serde_json::Value]) -> HotkeyAttachmentStats {
    HotkeyAttachmentStats {
        discovered: attachments.len() as i64,
        content_available: attachments
            .iter()
            .filter(|item| {
                item.get("content_available")
                    .and_then(|value| value.as_bool())
                    == Some(true)
            })
            .count() as i64,
        unknown: attachments
            .iter()
            .filter(|item| {
                item.get("token_status").and_then(|value| value.as_str()) == Some("unknown")
            })
            .count() as i64,
        unsupported: attachments
            .iter()
            .filter(|item| {
                item.get("read_error")
                    .and_then(|value| value.as_str())
                    .map(|value| value.contains("unsupported"))
                    == Some(true)
            })
            .count() as i64,
    }
}

#[cfg(windows)]
fn codex_ui_attachment_names() -> Vec<String> {
    let script = r#"
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class NativeWin {
  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();
}
"@
$hwnd = [NativeWin]::GetForegroundWindow()
if ($hwnd -eq [IntPtr]::Zero) { exit 0 }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) { exit 0 }
$items = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$seen = @{}
foreach ($item in $items) {
  $name = $item.Current.Name
  if ([string]::IsNullOrWhiteSpace($name)) { continue }
  $matches = [regex]::Matches($name, '[^\\/:*?"<>|\s]+\.(?:log|csv|json|md|txt|py|ts|tsx|js|jsx|java|sql|pdf|png|jpg|jpeg|docx|xlsx)', 'IgnoreCase')
  foreach ($match in $matches) {
    $value = $match.Value.Trim()
    if ($value.Length -gt 3 -and -not $seen.ContainsKey($value)) {
      $seen[$value] = $true
      Write-Output $value
    }
  }
}
"#;
    let output = Command::new("powershell")
        .creation_flags(CREATE_NO_WINDOW)
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ])
        .output();
    let Ok(output) = output else {
        return Vec::new();
    };
    if !output.status.success() {
        return Vec::new();
    }
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(|line| line.trim().to_string())
        .filter(|line| supported_or_known_extension(line))
        .collect()
}

#[cfg(not(windows))]
fn codex_ui_attachment_names() -> Vec<String> {
    Vec::new()
}

fn file_path_candidates(prompt: &str) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    for token in prompt.split_whitespace() {
        add_path_candidate(token, &mut candidates);
    }

    let mut quoted = String::new();
    let mut in_quote = false;
    for ch in prompt.chars() {
        if ch == '"' || ch == '\'' {
            if in_quote {
                add_path_candidate(&quoted, &mut candidates);
                quoted.clear();
            }
            in_quote = !in_quote;
            continue;
        }
        if in_quote {
            quoted.push(ch);
        }
    }
    candidates
}

fn add_path_candidate(raw: &str, candidates: &mut Vec<PathBuf>) {
    let trimmed = raw.trim_matches(|ch: char| {
        matches!(
            ch,
            '"' | '\'' | '`' | '<' | '>' | '(' | ')' | '[' | ']' | '{' | '}' | ',' | ';'
        )
    });
    if trimmed.len() < 4 {
        return;
    }
    let looks_like_path = trimmed.contains('\\')
        || trimmed.contains('/')
        || trimmed.contains(":\\")
        || supported_or_known_extension(trimmed);
    if !looks_like_path {
        return;
    }
    let path = PathBuf::from(trimmed);
    if path.exists() && path.is_file() && !candidates.iter().any(|item| item == &path) {
        candidates.push(path);
    }
}

fn resolve_attached_file_name(name: &str, prompt: &str) -> Option<PathBuf> {
    let direct = PathBuf::from(name);
    if direct.exists() && direct.is_file() {
        return Some(direct);
    }

    let mut matches = Vec::new();
    let mut visited_files = 0usize;
    for root in attachment_search_roots(prompt) {
        find_named_file(&root, name, 0, &mut visited_files, &mut matches);
        if matches.len() > 1 || visited_files > 12_000 {
            break;
        }
    }
    if matches.len() == 1 {
        matches.pop()
    } else {
        None
    }
}

fn attachment_search_roots(prompt: &str) -> Vec<PathBuf> {
    let mut roots = Vec::new();
    for raw in env::var("SCROOGE_ATTACHMENT_SEARCH_ROOTS")
        .unwrap_or_default()
        .split(';')
    {
        add_search_root(PathBuf::from(raw.trim()), &mut roots);
    }
    if let Ok(current) = env::current_dir() {
        add_search_root(current, &mut roots);
    }
    for path in file_path_candidates(prompt) {
        if let Some(parent) = path.parent() {
            add_search_root(parent.to_path_buf(), &mut roots);
        }
    }
    if let Ok(profile) = env::var("USERPROFILE") {
        let profile = PathBuf::from(profile);
        add_search_root(profile.join("Documents"), &mut roots);
        add_search_root(profile.join("Desktop"), &mut roots);
        add_search_root(profile.join("Downloads"), &mut roots);
    }
    add_search_root(PathBuf::from(r"C:\Mac\Home\Documents"), &mut roots);
    add_search_root(PathBuf::from(r"\\Mac\Home\Documents"), &mut roots);
    roots
}

fn add_search_root(path: PathBuf, roots: &mut Vec<PathBuf>) {
    if path.as_os_str().is_empty() || !path.exists() || !path.is_dir() {
        return;
    }
    let normalized = fs::canonicalize(&path).unwrap_or(path);
    if !roots.iter().any(|item| item == &normalized) {
        roots.push(normalized);
    }
}

fn find_named_file(
    root: &Path,
    name: &str,
    depth: usize,
    visited_files: &mut usize,
    matches: &mut Vec<PathBuf>,
) {
    if depth > 5 || *visited_files > 12_000 || matches.len() > 1 || should_skip_dir(root) {
        return;
    }
    let Ok(entries) = fs::read_dir(root) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() {
            *visited_files += 1;
            if path
                .file_name()
                .and_then(|value| value.to_str())
                .map(|value| value.eq_ignore_ascii_case(name))
                == Some(true)
            {
                matches.push(path);
                if matches.len() > 1 {
                    return;
                }
            }
        } else if path.is_dir() {
            find_named_file(&path, name, depth + 1, visited_files, matches);
            if matches.len() > 1 || *visited_files > 12_000 {
                return;
            }
        }
    }
}

fn should_skip_dir(path: &Path) -> bool {
    path.file_name()
        .and_then(|value| value.to_str())
        .map(|name| {
            let lowered = name.to_ascii_lowercase();
            matches!(
                lowered.as_str(),
                ".git"
                    | "node_modules"
                    | "target"
                    | ".venv"
                    | "venv"
                    | "__pycache__"
                    | "appdata"
                    | "library"
                    | ".cache"
                    | "windows"
                    | "program files"
                    | "program files (x86)"
            )
        })
        .unwrap_or(false)
}

fn attachment_from_path(path: &Path, discovery_source: &str) -> serde_json::Value {
    let name = display_name(path);
    let size_bytes = fs::metadata(path)
        .map(|metadata| metadata.len())
        .unwrap_or(0);
    if !is_supported_text_path(path) {
        return serde_json::json!({
            "name": name,
            "mime_type": mime_type_for(path),
            "size_bytes": size_bytes,
            "token_status": "unknown",
            "discovery_source": discovery_source,
            "content_available": false,
            "path_available": true,
            "read_error": "unsupported_attachment_type"
        });
    }
    if size_bytes > 2_000_000 {
        return serde_json::json!({
            "name": name,
            "mime_type": mime_type_for(path),
            "size_bytes": size_bytes,
            "token_status": "unknown",
            "discovery_source": discovery_source,
            "content_available": false,
            "path_available": true,
            "read_error": "attachment_file_too_large"
        });
    }
    match fs::read_to_string(path) {
        Ok(content) => serde_json::json!({
            "name": name,
            "mime_type": mime_type_for(path),
            "size_bytes": size_bytes,
            "content": content,
            "token_status": "unknown",
            "discovery_source": discovery_source,
            "content_available": true,
            "path_available": true
        }),
        Err(error) => serde_json::json!({
            "name": name,
            "mime_type": mime_type_for(path),
            "size_bytes": size_bytes,
            "token_status": "unknown",
            "discovery_source": discovery_source,
            "content_available": false,
            "path_available": true,
            "read_error": format!("read_failed:{error}")
        }),
    }
}

fn mentions_attachment(prompt: &str) -> bool {
    let lowered = prompt.to_lowercase();
    [
        "attachment",
        "attached",
        "uploaded",
        "file",
        "files",
        "첨부",
        "첨부한",
        "파일",
        "업로드",
    ]
    .iter()
    .any(|term| lowered.contains(term))
}

fn supported_or_known_extension(value: &str) -> bool {
    Path::new(value)
        .extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| {
            matches!(
                extension.to_ascii_lowercase().as_str(),
                "csv"
                    | "json"
                    | "log"
                    | "md"
                    | "txt"
                    | "py"
                    | "ts"
                    | "tsx"
                    | "js"
                    | "jsx"
                    | "java"
                    | "sql"
                    | "pdf"
                    | "png"
                    | "jpg"
                    | "jpeg"
                    | "docx"
                    | "xlsx"
            )
        })
        .unwrap_or(false)
}

fn is_supported_text_path(path: &Path) -> bool {
    path.extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| {
            matches!(
                extension.to_ascii_lowercase().as_str(),
                "csv"
                    | "json"
                    | "log"
                    | "md"
                    | "txt"
                    | "py"
                    | "ts"
                    | "tsx"
                    | "js"
                    | "jsx"
                    | "java"
                    | "sql"
            )
        })
        .unwrap_or(false)
}

fn mime_type_for(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| extension.to_ascii_lowercase())
        .as_deref()
    {
        Some("csv") => "text/csv",
        Some("json") => "application/json",
        Some("md") => "text/markdown",
        Some("py") => "text/x-python",
        Some("ts") | Some("tsx") => "application/typescript",
        Some("js") | Some("jsx") => "application/javascript",
        Some("java") => "text/x-java-source",
        Some("sql") => "application/sql",
        Some("log") | Some("txt") => "text/plain",
        Some("png") => "image/png",
        Some("jpg") | Some("jpeg") => "image/jpeg",
        Some("pdf") => "application/pdf",
        Some("docx") => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        Some("xlsx") => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        _ => "application/octet-stream",
    }
}

fn display_name(path: &Path) -> String {
    path.file_name()
        .and_then(|name| name.to_str())
        .map(|name| name.to_string())
        .unwrap_or_else(|| path.display().to_string())
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
