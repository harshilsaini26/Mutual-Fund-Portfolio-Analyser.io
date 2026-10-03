import { Composition, Folder } from "remotion";
import { EndScene } from "./EndScene";
import { ShotScene } from "./ShotScene";
import { FPS, HEIGHT, WIDTH } from "./theme";
import { TitleScene } from "./TitleScene";
import { Tour } from "./Tour";

// Nine scenes of 75 frames, eight 12-frame fades between them: 9 * 75 - 8 * 12.
const TOUR_FRAMES = 579;

export const RemotionRoot: React.FC = () => (
  <>
    <Folder name="Tour-Scenes">
      <Composition id="Title" component={TitleScene} width={WIDTH} height={HEIGHT} fps={FPS} durationInFrames={75} />
      <Composition
        id="Shot"
        component={ShotScene}
        width={WIDTH}
        height={HEIGHT}
        fps={FPS}
        durationInFrames={75}
        defaultProps={{ shot: "home", eyebrow: "The front page", caption: "Three ways in, and what the site is for" }}
      />
      <Composition id="End" component={EndScene} width={WIDTH} height={HEIGHT} fps={FPS} durationInFrames={75} />
    </Folder>
    <Composition id="Tour" component={Tour} width={WIDTH} height={HEIGHT} fps={FPS} durationInFrames={TOUR_FRAMES} />
  </>
);
