type OpenRingMarkProps = {
  className?: string;
  variant?: "mark" | "hero";
};

export function OpenRingMark({
  className = "",
  variant = "mark",
}: OpenRingMarkProps) {
  return (
    <span
      aria-hidden="true"
      className={`open-ring open-ring--${variant} ${className}`.trim()}
    >
      <span className="open-ring__arc open-ring__arc--outer" />
      <span className="open-ring__arc open-ring__arc--middle" />
      <span className="open-ring__arc open-ring__arc--inner" />
      {variant === "hero" ? (
        <span className="open-ring__core">
          看见
          <br />
          理解
          <br />
          选择
        </span>
      ) : (
        <span className="open-ring__dot" />
      )}
    </span>
  );
}
