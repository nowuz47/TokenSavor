const OPERATORS = new Set(["+", "-", "*", "/", "%", "^"]);
const PRECEDENCE = { "+": 1, "-": 1, "*": 2, "/": 2, "%": 2, "^": 3 };
const RIGHT_ASSOCIATIVE = new Set(["^"]);

export function calculate(expression) {
  const tokens = tokenize(expression);
  if (tokens.length === 0) {
    throw new Error("Enter an expression.");
  }
  return evaluateRpn(toRpn(tokens));
}

export function tokenize(expression) {
  const tokens = [];
  let index = 0;
  let expectsUnary = true;

  while (index < expression.length) {
    const char = expression[index];
    if (/\s/.test(char)) {
      index += 1;
      continue;
    }

    if (/[0-9.]/.test(char)) {
      const start = index;
      index += 1;
      while (index < expression.length && /[0-9.]/.test(expression[index])) index += 1;
      const raw = expression.slice(start, index);
      if (!/^\d+(\.\d+)?$|^\.\d+$/.test(raw)) {
        throw new Error(`Invalid number: ${raw}`);
      }
      tokens.push({ type: "number", value: Number(raw) });
      expectsUnary = false;
      continue;
    }

    if (char === "(" || char === ")") {
      tokens.push({ type: char });
      expectsUnary = char !== ")";
      index += 1;
      continue;
    }

    if (OPERATORS.has(char)) {
      if (char === "-" && expectsUnary) {
        tokens.push({ type: "number", value: 0 });
      } else if (expectsUnary) {
        throw new Error(`Unexpected operator: ${char}`);
      }
      tokens.push({ type: "operator", value: char });
      expectsUnary = true;
      index += 1;
      continue;
    }

    throw new Error(`Unsupported character: ${char}`);
  }

  return tokens;
}

function toRpn(tokens) {
  const output = [];
  const operators = [];

  for (const token of tokens) {
    if (token.type === "number") {
      output.push(token);
      continue;
    }

    if (token.type === "operator") {
      while (operators.length > 0) {
        const top = operators.at(-1);
        if (!top || top.type !== "operator") break;
        const tighter = PRECEDENCE[top.value] > PRECEDENCE[token.value];
        const equalAndLeft = PRECEDENCE[top.value] === PRECEDENCE[token.value] &&
          !RIGHT_ASSOCIATIVE.has(token.value);
        if (!tighter && !equalAndLeft) break;
        output.push(operators.pop());
      }
      operators.push(token);
      continue;
    }

    if (token.type === "(") {
      operators.push(token);
      continue;
    }

    if (token.type === ")") {
      while (operators.length > 0 && operators.at(-1).type !== "(") {
        output.push(operators.pop());
      }
      if (operators.length === 0) {
        throw new Error("Mismatched parentheses.");
      }
      operators.pop();
    }
  }

  while (operators.length > 0) {
    const token = operators.pop();
    if (token.type === "(" || token.type === ")") {
      throw new Error("Mismatched parentheses.");
    }
    output.push(token);
  }

  return output;
}

function evaluateRpn(tokens) {
  const stack = [];

  for (const token of tokens) {
    if (token.type === "number") {
      stack.push(token.value);
      continue;
    }

    const right = stack.pop();
    const left = stack.pop();
    if (left === undefined || right === undefined) {
      throw new Error("Incomplete expression.");
    }
    stack.push(applyOperator(token.value, left, right));
  }

  if (stack.length !== 1) {
    throw new Error("Incomplete expression.");
  }
  return stack[0];
}

function applyOperator(operator, left, right) {
  if ((operator === "/" || operator === "%") && right === 0) {
    throw new Error("Cannot divide by zero.");
  }

  switch (operator) {
    case "+":
      return left + right;
    case "-":
      return left - right;
    case "*":
      return left * right;
    case "/":
      return left / right;
    case "%":
      return left % right;
    case "^":
      return left ** right;
    default:
      throw new Error(`Unsupported operator: ${operator}`);
  }
}
