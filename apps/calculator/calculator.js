(() => {
  const display = document.getElementById("display");
  const keys = document.querySelector(".keys");

  const state = {
    current: "0",
    previous: null,
    operator: null,
    justEvaluated: false,
  };

  const MAX_LEN = 12;

  const format = (value) => {
    if (value === "Error") return value;
    const num = Number(value);
    if (!isFinite(num)) return "Error";
    const str = String(value);
    if (str.length <= MAX_LEN) return str;
    return num.toPrecision(MAX_LEN - 2).replace(/\.?0+(e|$)/, "$1");
  };

  const render = () => {
    display.textContent = format(state.current);
    document.querySelectorAll(".key-op").forEach((btn) => {
      btn.classList.toggle(
        "active",
        state.operator !== null &&
          btn.dataset.op === state.operator &&
          state.justEvaluated === false &&
          state.current === "0"
      );
    });
  };

  const inputDigit = (d) => {
    if (state.justEvaluated) {
      state.current = d;
      state.previous = null;
      state.operator = null;
      state.justEvaluated = false;
      return;
    }
    if (state.current === "0") {
      state.current = d;
    } else if (state.current.replace(/[-.]/g, "").length < MAX_LEN) {
      state.current += d;
    }
  };

  const inputDecimal = () => {
    if (state.justEvaluated) {
      state.current = "0.";
      state.previous = null;
      state.operator = null;
      state.justEvaluated = false;
      return;
    }
    if (!state.current.includes(".")) {
      state.current += ".";
    }
  };

  const compute = (a, b, op) => {
    switch (op) {
      case "+": return a + b;
      case "-": return a - b;
      case "*": return a * b;
      case "/": return b === 0 ? NaN : a / b;
      default: return b;
    }
  };

  const setOperator = (op) => {
    if (state.current === "Error") return;
    const currentNum = parseFloat(state.current);
    if (state.previous !== null && state.operator && !state.justEvaluated) {
      const result = compute(state.previous, currentNum, state.operator);
      if (!isFinite(result)) {
        state.current = "Error";
        state.previous = null;
        state.operator = null;
        return;
      }
      state.previous = result;
      state.current = String(result);
    } else {
      state.previous = currentNum;
    }
    state.operator = op;
    state.justEvaluated = false;
    state.current = "0";
  };

  const equals = () => {
    if (state.operator === null || state.previous === null) return;
    const result = compute(
      state.previous,
      parseFloat(state.current),
      state.operator
    );
    if (!isFinite(result)) {
      state.current = "Error";
    } else {
      state.current = String(result);
    }
    state.previous = null;
    state.operator = null;
    state.justEvaluated = true;
  };

  const clearAll = () => {
    state.current = "0";
    state.previous = null;
    state.operator = null;
    state.justEvaluated = false;
  };

  const toggleSign = () => {
    if (state.current === "0" || state.current === "Error") return;
    state.current = state.current.startsWith("-")
      ? state.current.slice(1)
      : "-" + state.current;
  };

  const percent = () => {
    if (state.current === "Error") return;
    state.current = String(parseFloat(state.current) / 100);
  };

  keys.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const { action, digit, op } = btn.dataset;
    switch (action) {
      case "digit": inputDigit(digit); break;
      case "decimal": inputDecimal(); break;
      case "operator": setOperator(op); break;
      case "equals": equals(); break;
      case "clear": clearAll(); break;
      case "sign": toggleSign(); break;
      case "percent": percent(); break;
    }
    render();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key >= "0" && e.key <= "9") inputDigit(e.key);
    else if (e.key === ".") inputDecimal();
    else if (["+", "-", "*", "/"].includes(e.key)) setOperator(e.key);
    else if (e.key === "Enter" || e.key === "=") { e.preventDefault(); equals(); }
    else if (e.key === "Escape") clearAll();
    else if (e.key === "%") percent();
    else if (e.key === "Backspace") {
      if (state.justEvaluated || state.current === "Error") clearAll();
      else if (state.current.length > 1) state.current = state.current.slice(0, -1);
      else state.current = "0";
    } else return;
    render();
  });

  render();
})();
