// Web worker that owns the HiGHS WebAssembly solver so the page stays responsive.
import highsLoader from "highs";
import highsWasm from "../../node_modules/highs/build/highs.wasm?url";
import { type DayProblem, type Highs, solveDay } from "./optimizer";

let highs: Promise<Highs> | null = null;

self.onmessage = async (e: MessageEvent<{ id: number; problem: DayProblem }>) => {
  const { id, problem } = e.data;
  try {
    highs ??= highsLoader({ locateFile: () => highsWasm }) as Promise<Highs>;
    const plan = solveDay(await highs, problem);
    self.postMessage({ id, plan });
  } catch (err) {
    self.postMessage({ id, error: err instanceof Error ? err.message : String(err) });
  }
};
