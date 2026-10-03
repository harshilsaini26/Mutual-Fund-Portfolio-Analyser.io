import { AbsoluteFill, Interactive, interpolate, useCurrentFrame } from "remotion";
import { FONT } from "./theme";

// The closing card: what it costs, where the data comes from, and where it lives.
export const EndScene: React.FC = () => {
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
        name="Promise"
        style={{
          fontSize: 56,
          fontWeight: 700,
          lineHeight: 1.15,
          color: "#eef2f8",
          opacity: interpolate(frame, [0, 14], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        Free. Public data, rebuilt every night. Nothing you enter leaves your browser.
      </Interactive.Div>
      <Interactive.Div
        name="Address"
        style={{
          marginTop: 36,
          fontSize: 30,
          color: "#8fb4ff",
          opacity: interpolate(frame, [12, 26], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        harshilsaini26.github.io/Mutual-Fund-Portfolio-Analyser.io
      </Interactive.Div>
    </AbsoluteFill>
  );
};
