import { DUMMY_SCORECARD } from "../data/dummy";

export function ScorecardView() {
  const data = DUMMY_SCORECARD;

  return (
    <div className="screen score-screen">
      <div className="section-head">
        <div>
          <h2>Retrofit feasibility</h2>
          <p className="muted">T0 software-only vs T1 clamp-on package — benchmark + payback</p>
        </div>
      </div>

      <div className="score-grid">
        <section className="panel">
          <h3>T0 vs T1 capability</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Capability</th>
                <th>T0 Legacy</th>
                <th>T1 Retrofit</th>
              </tr>
            </thead>
            <tbody>
              {data.t0_vs_t1.map((row) => (
                <tr key={row.capability}>
                  <td>{row.capability}</td>
                  <td>{row.t0}</td>
                  <td className="accent-text">{row.t1}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <h3>Validation score</h3>
          <p className="big-score">
            {data.composite_score}
            <span>/100</span>
          </p>
          <ul className="proj">
            <li>
              <span>Event F1</span>
              <strong>{data.event_f1.toFixed(2)}</strong>
            </li>
            <li>
              <span>Precision</span>
              <strong>{data.precision.toFixed(2)}</strong>
            </li>
            <li>
              <span>Fault-type recall</span>
              <strong>{(data.fault_type_recall * 100).toFixed(1)}%</strong>
            </li>
            <li>
              <span>Timeliness</span>
              <strong>{data.timeliness.toFixed(2)}</strong>
            </li>
            <li>
              <span>False alarms</span>
              <strong className="ok-text">{data.false_alarms}</strong>
            </li>
          </ul>
        </section>

        <section className="panel">
          <h3>Hardware BOM (per pump)</h3>
          <ul className="proj">
            {data.hardware_bom.map((row) => (
              <li key={row.item}>
                <span>{row.item}</span>
                <strong>€{row.eur}</strong>
              </li>
            ))}
            <li className="total">
              <span>Typical T1 kit</span>
              <strong>€{data.hardware_bom.reduce((s, r) => s + r.eur, 0)}</strong>
            </li>
          </ul>
          <p className="muted">Galvanically isolated · zero PLC code change</p>
        </section>

        <section className="panel">
          <h3>Fleet economics</h3>
          <ul className="proj">
            {data.economics.map((row) => (
              <li key={row.metric}>
                <span>{row.metric}</span>
                <strong>{row.value}</strong>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
