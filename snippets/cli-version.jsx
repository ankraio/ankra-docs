export const CliVersion = ({ since, command, note }) => {
  const latestStableCli = "0.13.0";
  const parse = (version) => String(version).split(".").map((part) => parseInt(part, 10) || 0);
  const requested = parse(since);
  const stable = parse(latestStableCli);
  let isPrerelease = false;
  for (let index = 0; index < 3; index += 1) {
    if (requested[index] > stable[index]) {
      isPrerelease = true;
      break;
    }
    if (requested[index] < stable[index]) {
      break;
    }
  }
  const containerStyle = {
    display: "flex",
    alignItems: "baseline",
    gap: "0.6rem",
    margin: "1rem 0",
    padding: "0.6rem 0.9rem",
    border: "1px solid rgba(128, 128, 128, 0.35)",
    borderRadius: "0.5rem",
    fontSize: "0.9em",
    lineHeight: 1.5,
  };
  const pillStyle = {
    flex: "none",
    padding: "0.1rem 0.5rem",
    borderRadius: "999px",
    background: "rgba(128, 128, 128, 0.18)",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
    fontSize: "0.85em",
    fontWeight: 600,
    whiteSpace: "nowrap",
  };
  const keepTogether = { whiteSpace: "nowrap" };
  return (
    <div style={containerStyle} data-cli-version={since}>
      <span style={pillStyle}>CLI v{since}+</span>
      <span>
        {command ? (
          <span>
            <span style={keepTogether}>
              <code>ankra {command}</code>
            </span>{" "}
            needs
          </span>
        ) : (
          <span>The commands on this page need</span>
        )}{" "}
        the ankra CLI <strong style={keepTogether}>v{since} or later</strong>
        {isPrerelease ? (
          <span>
            {" "}
            - a pre-release today, so enable the{" "}
            <a href="/integrations/ankra-cli#beta-pre-release-channel">beta channel</a> before
            upgrading
          </span>
        ) : null}
        . Check yours with{" "}
        <span style={keepTogether}>
          <code>ankra --version</code>
        </span>
        ; <a href="/integrations/ankra-cli#upgrading-the-cli">upgrade</a> with{" "}
        <span style={keepTogether}>
          <code>ankra upgrade</code>
        </span>
        .{note ? <span> {note}</span> : null}
      </span>
    </div>
  );
};
