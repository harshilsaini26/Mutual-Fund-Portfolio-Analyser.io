import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { EndScene } from "./EndScene";
import { ShotScene } from "./ShotScene";
import { TitleScene } from "./TitleScene";

// The README's tour of the public site: a title, seven pages, a closing card.
export const Tour: React.FC = () => (
  <TransitionSeries>
    <TransitionSeries.Sequence name="Title" durationInFrames={75}>
      <TitleScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
    <TransitionSeries.Sequence name="Front page" durationInFrames={75}>
      <ShotScene shot="home" eyebrow="The front page" caption="Three ways in, and what the site is for" />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
    <TransitionSeries.Sequence name="Look up a fund" durationInFrames={75}>
      <ShotScene shot="home-lookup" eyebrow="Look up a fund" caption="Each fund set against its category" />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
    <TransitionSeries.Sequence name="Fund page" durationInFrames={75}>
      <ShotScene shot="fund" eyebrow="A fund page" caption="Returns, falls, costs and holdings" />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
    <TransitionSeries.Sequence name="Explore funds" durationInFrames={75}>
      <ShotScene shot="funds" eyebrow="Explore funds" caption="Every fund in one sortable list" />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
    <TransitionSeries.Sequence name="Compare" durationInFrames={75}>
      <ShotScene shot="compare" eyebrow="Compare" caption="Up to four funds, side by side" />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
    <TransitionSeries.Sequence name="Your portfolio" durationInFrames={75}>
      <ShotScene shot="portfolio" eyebrow="Your portfolio" caption="What your funds add up to, company by company" />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
    <TransitionSeries.Sequence name="Privacy" durationInFrames={75}>
      <ShotScene shot="home-privacy" eyebrow="Your data stays yours" caption="Nothing you enter leaves your browser" />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
    <TransitionSeries.Sequence name="End" durationInFrames={75}>
      <EndScene />
    </TransitionSeries.Sequence>
  </TransitionSeries>
);
