import {
  AbsoluteFill,
  Easing,
  Img,
  Interactive,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { FONT } from "./theme";

export type ShotProps = {
  shot: string;
  eyebrow: string;
  caption: string;
};

// One page of the site: its name and one line on top, the screenshot in a quiet
// browser frame below. Still once it has risen into place: a GIF stays small only
// when most of each frame repeats the last.
export const ShotScene: React.FC<ShotProps> = ({ shot, eyebrow, caption }) => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{ backgroundColor: "#0f1b2d", fontFamily: FONT }}>
      <Interactive.Div
        name="Eyebrow"
        style={{
          position: "absolute",
          left: 96,
          top: 52,
          fontSize: 26,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "#8fb4ff",
          opacity: interpolate(frame, [0, 10], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        {eyebrow}
      </Interactive.Div>
      <Interactive.Div
        name="Caption"
        style={{
          position: "absolute",
          left: 96,
          right: 96,
          top: 88,
          fontSize: 50,
          fontWeight: 700,
          lineHeight: 1.1,
          color: "#eef2f8",
          opacity: interpolate(frame, [4, 16], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        {caption}
      </Interactive.Div>
      <Interactive.Div
        name="Browser"
        style={{
          position: "absolute",
          left: 140,
          top: 184,
          width: 1000,
          borderRadius: 14,
          overflow: "hidden",
          backgroundColor: "#ffffff",
          boxShadow: "0 30px 80px rgba(0, 0, 0, 0.45)",
          transformOrigin: "50% 0%",
          translate: interpolate(frame, [0, 18], ["0px 48px", "0px 0px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
        }}
      >
        <Interactive.Div
          name="Browser bar"
          style={{
            height: 26,
            display: "flex",
            alignItems: "center",
            gap: 8,
            paddingLeft: 14,
            backgroundColor: "#e6ebf3",
          }}
        >
          <Interactive.Div name="Dot 1" style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: "#c3cbd8" }} />
          <Interactive.Div name="Dot 2" style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: "#c3cbd8" }} />
          <Interactive.Div name="Dot 3" style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: "#c3cbd8" }} />
        </Interactive.Div>
        <Img
          name="Screenshot"
          src={staticFile(`shots/${shot}.png`)}
          style={{ display: "block", width: 1000, height: 625 }}
        />
      </Interactive.Div>
    </AbsoluteFill>
  );
};
