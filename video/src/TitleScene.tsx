import { AbsoluteFill, Easing, Interactive, interpolate, useCurrentFrame } from "remotion";
import { FONT } from "./theme";

// The opening card: what the site is, in its own words.
export const TitleScene: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0f1b2d",
        fontFamily: FONT,
        justifyContent: "center",
        paddingLeft: 120,
        paddingRight: 120,
      }}
    >
      <Interactive.Div
        name="Name"
        style={{
          fontSize: 30,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "#8fb4ff",
          opacity: interpolate(frame, [0, 12], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        Look-through
      </Interactive.Div>
      <Interactive.Div
        name="Headline"
        style={{
          marginTop: 18,
          maxWidth: 1000,
          fontSize: 78,
          fontWeight: 700,
          lineHeight: 1.05,
          color: "#eef2f8",
          opacity: interpolate(frame, [6, 22], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
          translate: interpolate(frame, [6, 26], ["0px 24px", "0px 0px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
        }}
      >
        See what every Indian mutual fund owns, and how it has done
      </Interactive.Div>
    </AbsoluteFill>
  );
};
