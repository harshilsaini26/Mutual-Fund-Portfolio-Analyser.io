import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

// The site's own type: Terminess Nerd Font (Terminus by Dimitar Zhekov, SIL OFL 1.1),
// copied from src/m6_views/static/fonts/.
export const FONT = "Terminess Nerd Font";

// @remotion/fonts holds each render until the font has loaded.
Promise.all([
  loadFont({ family: FONT, url: staticFile("fonts/terminess-Regular.woff2"), weight: "400" }),
  loadFont({ family: FONT, url: staticFile("fonts/terminess-Bold.woff2"), weight: "700" }),
]);

export const FPS = 30;
export const WIDTH = 1280;
export const HEIGHT = 720;
