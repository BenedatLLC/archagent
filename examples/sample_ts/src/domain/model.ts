import { WIDGET } from "../ui/widget"; // BND-010 violation: domain must not import ui

export function describe(): string {
  const r = eval("1 + 1"); // STR-011 violation: no eval
  return WIDGET + String(r);
}
