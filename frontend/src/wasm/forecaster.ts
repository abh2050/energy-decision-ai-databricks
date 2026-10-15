// Browser forecaster: the pinned LightGBM models exported to ONNX (Gate 2), run with
// onnxruntime web. Features follow src/edip/core/features.py: for target hour t, load at
// t-24 and t-168, means of the 24 and 168 hours ending at t-24, and the Europe/Lisbon
// hour and weekday. Conformal corrections (version 2) widen P10 and P90 per UTC hour.
import * as ort from "onnxruntime-web/wasm";
import wasmUrl from "../../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm?url";
import mjsUrl from "../../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs?url";

ort.env.wasm.numThreads = 1; // no cross-origin isolation on GitHub Pages
ort.env.wasm.wasmPaths = { wasm: wasmUrl, mjs: mjsUrl };

export const QUANTITIES = ["point", "p10", "p50", "p90"] as const;
export type Quantity = (typeof QUANTITIES)[number];
export type DayForecast = Record<Quantity, number[]>;

const lisbon = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Lisbon",
  hour: "2-digit",
  hourCycle: "h23",
  weekday: "short",
});
const DOW: Record<string, number> = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };

function localHourDow(utcIso: string): [number, number] {
  const parts = lisbon.formatToParts(new Date(utcIso.replace(" ", "T") + "Z"));
  const hour = Number(parts.find((p) => p.type === "hour")!.value);
  const dow = DOW[parts.find((p) => p.type === "weekday")!.value];
  return [hour, dow];
}

const mean = (xs: number[]) => xs.reduce((a, x) => a + x, 0) / xs.length;

/** Feature rows for 24 target hours starting at series index `start` (needs 192 h before). */
export function features(load: number[], hoursUtc: string[], start: number): Float32Array {
  if (start < 192) throw new Error("need 192 hours of history before the first target hour");
  const out = new Float32Array(24 * 6);
  for (let h = 0; h < 24; h++) {
    const i = start + h;
    const [hour, dow] = localHourDow(hoursUtc[i]);
    // Python builds features in float64 and the models were trained on float32-rounded
    // values; Float32Array rounds the same way.
    out.set(
      [
        load[i - 24],
        load[i - 168],
        mean(load.slice(i - 47, i - 23)),
        mean(load.slice(i - 191, i - 23)),
        hour,
        dow,
      ],
      h * 6,
    );
  }
  return out;
}

export class Forecaster {
  private constructor(
    private sessions: Record<Quantity, ort.InferenceSession>,
    private corrections: number[],
  ) {}

  static async load(base: string): Promise<Forecaster> {
    const sessions = {} as Record<Quantity, ort.InferenceSession>;
    for (const q of QUANTITIES) {
      sessions[q] = await ort.InferenceSession.create(`${base}data/models/load_forecaster_${q}.onnx`);
    }
    const cqr = await (await fetch(`${base}data/models/cqr_corrections.json`)).json();
    const corr = Array(24).fill(0);
    for (const r of cqr.per_hour) corr[r.horizon_h] = r.correction_kw;
    return new Forecaster(sessions, corr);
  }

  async day(load: number[], hoursUtc: string[], start: number): Promise<DayForecast> {
    const x = features(load, hoursUtc, start);
    const out = {} as DayForecast;
    for (const q of QUANTITIES) {
      const s = this.sessions[q];
      const res = await s.run({ [s.inputNames[0]]: new ort.Tensor("float32", x, [24, 6]) });
      out[q] = Array.from(res[s.outputNames[0]].data as Float32Array);
    }
    // Decision time is 00:00 UTC, so the forecast hour is the UTC hour (0 to 23).
    out.p10 = out.p10.map((v, h) => Math.min(v - this.corrections[h], out.p50[h]));
    out.p90 = out.p90.map((v, h) => Math.max(v + this.corrections[h], out.p50[h]));
    return out;
  }
}
