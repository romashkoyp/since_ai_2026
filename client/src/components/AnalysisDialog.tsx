import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, createAnalysis, fetchModelInfo } from "../api/client";
import type { AnalysisFileField, AnalysisRun, ModelInfo } from "../types/alerts";
import { Icon } from "./Icon";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Called after a successful run so the dashboard can reload */
  onCompleted: (run: AnalysisRun) => void;
}

interface FieldSpec {
  name: AnalysisFileField;
  label: string;
  help: string;
  required?: boolean;
  accept: string;
}

const TABLE = ".csv,.parquet,.json";

const FIELDS: FieldSpec[] = [
  { name: "datasheet", label: "Pump datasheet", help: "One row per pump: ratings and control type.", required: true, accept: TABLE },
  {
    name: "telemetry",
    label: "Telemetry to check",
    help: "Raw sensor readings (any rate) or 1-minute summaries.",
    required: true,
    accept: TABLE,
  },
  {
    name: "baseline",
    label: "Healthy baseline",
    help: "At least 24 h of normal running just before the telemetry. Without it the first day counts as normal.",
    accept: TABLE,
  },
  { name: "context", label: "Operating context", help: "Sea state and suction head over time.", accept: TABLE },
  { name: "snapshots", label: "Vibration snapshots", help: "Waveforms (parquet) for bearing and alignment checks.", accept: ".parquet" },
  {
    name: "events",
    label: "Known faults (to score)",
    help: "Optional answer sheet: asset_id, fault_type, onset_utc, end_utc. Marks each alert Pass or Fail.",
    accept: ".csv,.json",
  },
];

type Files = Partial<Record<AnalysisFileField, File>>;

const MB = 1_000_000; // decimal units, as macOS Finder / Windows Explorer show file sizes (and the server limit)

/** Human-readable size: 553 bytes · 12 KB · 6.6 MB · 1.2 GB */
function formatSize(bytes: number): string {
  if (bytes < 1000) return `${bytes} bytes`;
  if (bytes < 999_500) return `${Math.round(bytes / 1000)} KB`; // switch before it would round to "1000 KB"
  if (bytes < 999_950 * 1000) return `${(bytes / MB).toFixed(1)} MB`;
  return `${(bytes / (1000 * MB)).toFixed(1)} GB`;
}

export function AnalysisDialog({ open, onClose, onCompleted }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [files, setFiles] = useState<Files>({});
  const [useMl, setUseMl] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisRun | null>(null);
  const [formKey, setFormKey] = useState(0);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    if (!open || model) return;
    const ac = new AbortController();
    fetchModelInfo(ac.signal)
      .then(setModel)
      .catch(() => {
        /* the form still works; the server validates the upload */
      });
    return () => ac.abort();
  }, [open, model]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const maxBytes = (model?.max_upload_mb ?? Infinity) * MB;
  const tooBig = FIELDS.find((f) => (files[f.name]?.size ?? 0) > maxBytes);
  const canSubmit = !!files.datasheet && !!files.telemetry && !tooBig && !running && model?.available !== false;

  function reset() {
    setFiles({});
    setError(null);
    setResult(null);
    setFormKey((k) => k + 1);
  }

  /** Stops waiting for the response (the server may still finish and store the run) */
  function stop() {
    abortRef.current?.abort();
    setRunning(false);
  }

  function close() {
    stop();
    onClose();
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    const form = new FormData();
    for (const f of FIELDS) {
      const file = files[f.name];
      if (file) form.append(f.name, file, file.name);
    }
    form.append("use_ml", String(useMl));

    const ac = new AbortController();
    abortRef.current = ac;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const run = await createAnalysis(form, ac.signal);
      setResult(run);
      onCompleted(run);
    } catch (err) {
      if (ac.signal.aborted) return;
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not reach the server. Check the connection and try again.",
      );
    } finally {
      if (!ac.signal.aborted) setRunning(false);
    }
  }

  return (
    <dialog ref={dialogRef} className="analysis-dialog" onCancel={(e) => (running ? e.preventDefault() : close())} aria-labelledby="analysis-title">
      <form key={formKey} onSubmit={submit} className="analysis-form">
        <header className="analysis-head">
          <div>
            <h2 id="analysis-title">Analyse pump data</h2>
            <p className="hint">
              Runs the trained model
              {model?.model_version ? (
                <>
                  {" "}
                  <strong>{model.model_version}</strong>
                </>
              ) : null}{" "}
              (physics rules + ML) on your files. The dashboard then shows the new results.
            </p>
          </div>
          <button type="button" className="icon-btn" onClick={close} aria-label="Close" disabled={running}>
            <Icon name="back" size={16} />
          </button>
        </header>

        {model && !model.available && (
          <div className="notice" role="alert">
            <Icon name="warning" size={18} />
            <span>The model is not available on the server right now{model.reason ? `: ${model.reason}` : "."}</span>
          </div>
        )}

        <div className="file-grid">
          {FIELDS.map((f) => {
            const file = files[f.name];
            const over = file && file.size > maxBytes;
            return (
              <label key={f.name} className={`file-field ${file ? "has-file" : ""} ${over ? "invalid" : ""}`}>
                <span className="file-label">
                  {f.label}
                  {f.required ? <span className="req"> *</span> : <span className="opt"> optional</span>}
                </span>
                <input
                  type="file"
                  name={f.name}
                  accept={f.accept}
                  required={f.required}
                  disabled={running}
                  onChange={(e) => {
                    const next = e.target.files?.[0];
                    setFiles((prev) => ({ ...prev, [f.name]: next }));
                    setResult(null);
                    setError(null);
                  }}
                />
                <span className="file-help">
                  {over
                    ? `Too large (${formatSize(file.size)}); the limit is ${model?.max_upload_mb} MB.`
                    : file
                      ? `${file.name} · ${formatSize(file.size)}`
                      : f.help}
                </span>
              </label>
            );
          })}
        </div>

        {model?.required_datasheet_columns?.length ? (
          <details className="tech">
            <summary>Required datasheet columns</summary>
            <p className="hint mono">{model.required_datasheet_columns.join(", ")}</p>
          </details>
        ) : null}

        <label className="toggle">
          <input type="checkbox" checked={useMl} onChange={(e) => setUseMl(e.target.checked)} disabled={running} />
          <span>Use the ML diagnostician on top of the physics rules (recommended)</span>
        </label>

        {error && (
          <div className="notice notice-error" role="alert">
            <Icon name="alert" size={18} />
            <span>{error}</span>
          </div>
        )}

        {result && (
          <div className="analysis-result" role="status">
            <p>
              <Icon name="check" size={16} /> Checked <strong>{result.pumps}</strong> pump{result.pumps === 1 ? "" : "s"} and
              found <strong>{result.alerts}</strong> alert{result.alerts === 1 ? "" : "s"}
              {result.ml_overrides ? ` (${result.ml_overrides} named by the ML model)` : ""} in {result.processing_seconds}s.
            </p>
            {result.notes.length > 0 && (
              <ul className="analysis-notes">
                {result.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <footer className="analysis-actions">
          {result ? (
            <>
              <button type="button" className="btn btn-secondary" onClick={reset}>
                Analyse other files
              </button>
              <button type="button" className="btn btn-primary" onClick={close}>
                View results
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn btn-secondary" onClick={running ? stop : close}>
                {running ? "Stop" : "Cancel"}
              </button>
              <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
                <Icon name={running ? "refresh" : "upload"} size={16} className={running ? "spin" : ""} />
                {running ? "Running the model…" : "Run analysis"}
              </button>
            </>
          )}
        </footer>
      </form>
    </dialog>
  );
}
