import { calculate } from "./calculator-core.mjs";

const display = document.querySelector("[data-display]");
const expression = document.querySelector("[data-expression]");
const status = document.querySelector("[data-status]");
const keys = document.querySelectorAll("[data-key]");

let buffer = "";

keys.forEach((button) => {
  button.addEventListener("click", () => handleKey(button.dataset.key));
});

window.addEventListener("keydown", (event) => {
  if (/^[0-9+\-*/().%^]$/.test(event.key)) {
    handleKey(event.key);
  } else if (event.key === "Enter" || event.key === "=") {
    handleKey("=");
  } else if (event.key === "Backspace") {
    handleKey("backspace");
  } else if (event.key === "Escape") {
    handleKey("clear");
  }
});

function handleKey(key) {
  if (key === "clear") {
    buffer = "";
    render("0", "Ready");
    return;
  }

  if (key === "backspace") {
    buffer = buffer.slice(0, -1);
    render(buffer || "0", "Editing");
    return;
  }

  if (key === "=") {
    try {
      const result = calculate(buffer);
      render(formatResult(result), "Calculated");
      buffer = String(result);
    } catch (error) {
      render(buffer || "0", error.message, true);
    }
    return;
  }

  buffer += key;
  render(buffer, "Editing");
}

function render(value, message, isError = false) {
  display.textContent = value;
  expression.textContent = buffer || "No expression";
  status.textContent = message;
  status.classList.toggle("error", isError);
}

function formatResult(value) {
  if (!Number.isFinite(value)) return "Error";
  return Number.isInteger(value) ? String(value) : value.toFixed(8).replace(/0+$/, "").replace(/\.$/, "");
}
