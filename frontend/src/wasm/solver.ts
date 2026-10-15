// Promise wrapper around the optimizer web worker.
import type { DayProblem, Plan } from "./optimizer";

export class Solver {
  private worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
  private next = 1;
  private pending = new Map<number, { resolve: (p: Plan) => void; reject: (e: Error) => void }>();

  constructor() {
    this.worker.onmessage = (e: MessageEvent<{ id: number; plan?: Plan; error?: string }>) => {
      const p = this.pending.get(e.data.id);
      if (!p) return;
      this.pending.delete(e.data.id);
      if (e.data.error) p.reject(new Error(e.data.error));
      else p.resolve(e.data.plan!);
    };
  }

  solve(problem: DayProblem): Promise<Plan> {
    const id = this.next++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ id, problem });
    });
  }
}
