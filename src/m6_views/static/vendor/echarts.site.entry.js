// The ECharts this site draws with: six chart types, the components its options
// name, label layout and the SVG renderer (charts.js asks for "svg").
import * as echarts from "echarts/core";
import { LineChart, BarChart, ScatterChart, PieChart, SankeyChart, TreemapChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent, AxisPointerComponent,
         DataZoomComponent, MarkLineComponent, MarkPointComponent, AriaComponent } from "echarts/components";
import { LabelLayout } from "echarts/features";
import { SVGRenderer } from "echarts/renderers";
echarts.use([LineChart, BarChart, ScatterChart, PieChart, SankeyChart, TreemapChart,
             GridComponent, LegendComponent, TooltipComponent, AxisPointerComponent,
             DataZoomComponent, MarkLineComponent, MarkPointComponent, AriaComponent,
             LabelLayout, SVGRenderer]);
globalThis.echarts = echarts;
