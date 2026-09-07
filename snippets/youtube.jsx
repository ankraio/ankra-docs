export const YouTube = ({ id, title, start }) => {
  const wrapperStyle = {
    position: "relative",
    width: "100%",
    paddingBottom: "56.25%",
    margin: "1rem 0 1.5rem",
    borderRadius: "0.75rem",
    overflow: "hidden",
    border: "1px solid rgba(128, 128, 128, 0.35)",
    background: "rgba(128, 128, 128, 0.08)",
  };
  const frameStyle = {
    position: "absolute",
    top: 0,
    left: 0,
    width: "100%",
    height: "100%",
    border: 0,
  };
  const source =
    "https://www.youtube-nocookie.com/embed/" + id + "?rel=0" + (start ? "&start=" + start : "");
  return (
    <div style={wrapperStyle} data-youtube={id}>
      <iframe
        style={frameStyle}
        src={source}
        title={title || "Ankra video"}
        loading="lazy"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowFullScreen
        referrerPolicy="strict-origin-when-cross-origin"
      />
    </div>
  );
};
