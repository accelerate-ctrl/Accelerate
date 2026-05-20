# Simple Calculator

A standalone web calculator with no build step.

## Run

Open `index.html` in a browser, or serve the directory:

```sh
python3 -m http.server --directory apps/calculator 8000
```

Then visit http://localhost:8000.

## Features

- Add, subtract, multiply, divide
- Decimal input, sign toggle, percent
- Keyboard input (digits, `+ - * /`, `Enter`, `=`, `Esc`, `Backspace`, `%`)
- Chained operations (e.g. `2 + 3 * 4 =` evaluates left-to-right)
- Divide-by-zero shows `Error`
