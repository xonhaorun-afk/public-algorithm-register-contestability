import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const echarts = require('echarts');
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const data = JSON.parse(fs.readFileSync(path.join(root, 'outputs', 'chart_data.json'), 'utf8'));
const figureDir = path.join(root, 'figures');
fs.mkdirSync(figureDir, { recursive: true });

const C = { blue:'#3568B8', teal:'#2B8C82', amber:'#D38B2C', red:'#C94C4C', navy:'#23364D', gray:'#6C7A89', light:'#EDF2F7', grid:'#DCE4EC' };
const font = 'Noto Sans CJK SC, Microsoft YaHei, sans-serif';
const base = {
  backgroundColor: '#FFFFFF',
  textStyle: { fontFamily: font, color: C.navy },
  title: { left: 36, top: 22, textStyle: { fontSize: 25, fontWeight: 700, color: C.navy }, subtextStyle: { fontSize: 14, color: C.gray, lineHeight: 22 } },
};
function render(name, option, width=1280, height=760) {
  const chart = echarts.init(null, null, { renderer:'svg', ssr:true, width, height });
  chart.setOption({ ...base, ...option });
  const svg = chart.renderToSVGString();
  fs.writeFileSync(path.join(figureDir, `${name}.svg`), svg);
  chart.dispose();
}
const pct = v => Number(v).toFixed(v >= 10 ? 1 : 2) + '%';

// Figure 1: conceptual model, deliberately separate from outcome claims.
render('figure_1_disclosure_chain', {
  title: { text:'可争议性披露链：从“可见”到“可行动”', subtext:'测量公开信息的必要条件，不推断实际申诉、救济效果或公众信任' },
  series: [{
    type:'graph', layout:'none', left:180, right:180, top:120, bottom:70,
    edgeSymbol:['none','arrow'], edgeSymbolSize:[0,13],
    label:{ show:true, fontFamily:font, fontSize:16, lineHeight:25, color:'#FFFFFF', fontWeight:600 },
    edgeLabel:{ show:false },
    data:[
      { name:'知情\n简介＋目标', x:150, y:270, symbol:'roundRect', symbolSize:[190,104], itemStyle:{ color:C.blue } },
      { name:'理解\n数据＋技术＋风险', x:440, y:270, symbol:'roundRect', symbolSize:[210,104], itemStyle:{ color:C.teal } },
      { name:'质疑\n人工介入＋联系方式', x:730, y:270, symbol:'roundRect', symbolSize:[220,104], itemStyle:{ color:C.amber } },
      { name:'救济\n程序／期限／受理去向', x:1040, y:270, symbol:'roundRect', symbolSize:[225,104], itemStyle:{ color:C.red } },
      { name:'全站 FAQ：通用投诉与异议路径\n（条目外补充，不计入条目级导航）', x:1040, y:510, symbol:'roundRect', symbolSize:[330,86], label:{ color:C.navy, fontSize:14, lineHeight:22 }, itemStyle:{ color:'#E8EDF3', borderColor:'#9AA8B7', borderWidth:1, borderType:'dashed' } },
    ],
    links:[
      { source:0, target:1, lineStyle:{ color:'#8AA0B8', width:2, curveness:0 } },
      { source:1, target:2, lineStyle:{ color:'#8AA0B8', width:2, curveness:0 } },
      { source:2, target:3, lineStyle:{ color:'#8AA0B8', width:2, curveness:0 } },
      { source:4, target:3, lineStyle:{ color:'#9AA8B7', width:2, type:'dashed', curveness:0.12 } },
    ],
  }],
  graphic:[{ type:'text', left:70, bottom:30, style:{ text:'字段非占位 ≠ 内容充分；出现救济词 ≠ 具有可执行指引；完整披露链 ≠ 有效救济。', fill:C.gray, font:`14px ${font}` } }],
}, 1280, 680);

// Figure 2: full-population coverage with Wilson intervals in labels.
const coverageOrder = ['notice','explain','challenge','remedy_mention','remedy_guidance','chain_complete'];
const shortLabels = { notice:'知情', explain:'理解', challenge:'质疑', remedy_mention:'救济词汇', remedy_guidance:'救济导航（人工确认）', chain_complete:'完整披露链' };
const cov = coverageOrder.map(k => data.coverage.find(d => d.indicator === k));
render('figure_2_coverage', {
  title:{ text:'披露链各环节覆盖率', subtext:'荷兰国家算法登记册当前快照，N＝1,608；括号内为 Wilson 95% 置信区间' },
  grid:{ left:205, right:320, top:125, bottom:65 },
  xAxis:{ type:'value', min:0, max:100, name:'条目占比（%）', nameLocation:'middle', nameGap:38, axisLabel:{ formatter:'{value}%' }, splitLine:{ lineStyle:{ color:C.grid } } },
  yAxis:{ type:'category', inverse:true, data:cov.map(d => shortLabels[d.indicator]), axisLabel:{ fontSize:16 }, axisTick:{ show:false } },
  series:[{
    type:'bar', barWidth:32, data:cov.map(d => ({ value:d.percent, itemStyle:{ color:d.indicator.includes('remedy') || d.indicator==='chain_complete' ? C.red : C.blue }, label:{ position:d.percent > 85 ? 'insideRight' : 'right', color:d.percent > 85 ? '#FFFFFF' : C.navy, backgroundColor:d.percent > 85 ? 'transparent' : 'rgba(255,255,255,0.88)', padding:[3,5] } })),
    showBackground:true, backgroundStyle:{ color:'#F1F4F8' },
    label:{ show:true, fontSize:14, formatter:p => `${pct(p.value)}  [${pct(cov[p.dataIndex].wilson_low_pct)}, ${pct(cov[p.dataIndex].wilson_high_pct)}]` },
  }],
}, 1400, 720);

// Figure 3: risk category comparison, with a discrete scale suitable for rare outcomes.
const indicators = ['explain','challenge','remedy_mention','remedy_guidance'];
const cats = ['Hoog-risico AI-systeem','Impactvolle algoritmes','Overige algoritmes'];
const catLabels = { 'Hoog-risico AI-systeem':'高风险 AI', 'Impactvolle algoritmes':'有影响力算法', 'Overige algoritmes':'其他算法' };
const indLabels = { explain:'理解', challenge:'质疑', remedy_mention:'救济词汇', remedy_guidance:'救济导航' };
const heat = [];
cats.forEach((c,x) => indicators.forEach((i,y) => {
  const row = data.category.find(d => d.group === c && d.indicator === i);
  heat.push({ value:[x,y,row.percent], label:{ color:row.percent > 20 ? '#FFFFFF' : C.navy } });
}));
render('figure_3_category_heatmap', {
  title:{ text:'不同发布类别的披露率', subtext:'单元格为条目百分比；救济导航事件稀疏，类别差异不应作因果解释' },
  grid:{ left:150, right:70, top:140, bottom:110 },
  xAxis:{ type:'category', data:cats.map(c=>catLabels[c]), axisLabel:{ fontSize:15 }, axisTick:{ show:false } },
  yAxis:{ type:'category', data:indicators.map(i=>indLabels[i]), axisLabel:{ fontSize:15 }, axisTick:{ show:false } },
  visualMap:{ type:'piecewise', orient:'horizontal', left:'center', bottom:24, pieces:[{min:80,max:100,color:'#214F96',label:'80–100%'},{min:20,max:80,color:'#5B8BCB',label:'20–80%'},{min:5,max:20,color:'#A7C2E3',label:'5–20%'},{min:1,max:5,color:'#F1B4A8',label:'1–5%'},{min:0,max:1,color:'#F8DEDA',label:'0–1%'}], textStyle:{ color:C.gray } },
  series:[{ type:'heatmap', data:heat, label:{ show:true, fontSize:18, fontWeight:700, formatter:p=>pct(p.value[2]) }, itemStyle:{ borderColor:'#FFFFFF', borderWidth:5, borderRadius:5 } }],
}, 1180, 700);

// Figure 4: organizational templates and concentration among the 12 largest publishers.
const orgs = data.organizations;
const orgIndicators = [['explain_pct','理解'],['challenge_pct','质疑'],['remedy_mention_pct','救济词汇'],['remedy_guidance_pct','救济导航']];
const orgHeat = [];
orgs.forEach((o,y) => orgIndicators.forEach(([key],x) => orgHeat.push({ value:[x,y,o[key]], label:{ color:o[key] > 20 ? '#FFFFFF' : C.navy } })));
render('figure_4_organization_heatmap', {
  title:{ text:'条目数最多的12个机构：披露模式并不一致', subtext:'按当前条目数排序；救济词汇可表示监测投诉，并不等同于提供救济路径' },
  grid:{ left:250, right:65, top:135, bottom:100 },
  xAxis:{ type:'category', data:orgIndicators.map(d=>d[1]), axisLabel:{ fontSize:15 }, axisTick:{ show:false } },
  yAxis:{ type:'category', inverse:true, data:orgs.map(o=>o.organization.replace('Gemeente ','').replace('Stichting ','')), axisLabel:{ fontSize:13 }, axisTick:{ show:false } },
  visualMap:{ type:'piecewise', orient:'horizontal', left:'center', bottom:20, pieces:[{min:80,max:100,color:'#214F96',label:'80–100%'},{min:20,max:80,color:'#5B8BCB',label:'20–80%'},{min:5,max:20,color:'#A7C2E3',label:'5–20%'},{min:1,max:5,color:'#F1B4A8',label:'1–5%'},{min:0,max:1,color:'#F8DEDA',label:'0–1%'}], textStyle:{ color:C.gray } },
  series:[{ type:'heatmap', data:orgHeat, label:{ show:true, fontSize:13, fontWeight:600, formatter:p=>pct(p.value[2]) }, itemStyle:{ borderColor:'#FFFFFF', borderWidth:4, borderRadius:4 } }],
}, 1250, 850);

// Figure 5: within-standard paired first/last comparison.
const pairInds = ['notice','explain','challenge','remedy_mention'];
const pairLabels = { notice:'知情', explain:'理解', challenge:'质疑', remedy_mention:'救济词汇' };
const pairs = pairInds.map(i => data.paired.find(d=>d.indicator===i));
const pairData = pairs.map((d,i)=>[i,d.first_percent,d.last_percent,d.change_pp]);
render('figure_5_paired_change', {
  title:{ text:'同一发布标准内的首末版本配对变化', subtext:'539个具有至少两个1.0版本且有发布日期的算法；圆点为首版／末版，连线仅表示方向' },
  grid:{ left:110, right:70, top:140, bottom:85 },
  xAxis:{ type:'category', data:pairInds.map(i=>pairLabels[i]), axisLabel:{ fontSize:16 }, axisTick:{ show:false } },
  yAxis:{ type:'value', min:0, max:100, name:'条目占比（%）', axisLabel:{ formatter:'{value}%' }, splitLine:{ lineStyle:{ color:C.grid } } },
  series:[{
    type:'custom', data:pairData,
    renderItem:(params,api)=>{
      const x=api.coord([api.value(0),0])[0];
      const p1=api.coord([api.value(0),api.value(1)]);
      const p2=api.coord([api.value(0),api.value(2)]);
      const delta=api.value(3);
      return { type:'group', children:[
        { type:'line', shape:{ x1:p1[0],y1:p1[1],x2:p2[0],y2:p2[1] }, style:{ stroke:delta>=0?C.teal:C.red, lineWidth:5 } },
        { type:'circle', shape:{ cx:p1[0],cy:p1[1],r:9 }, style:{ fill:'#FFFFFF', stroke:C.gray, lineWidth:3 } },
        { type:'circle', shape:{ cx:p2[0],cy:p2[1],r:10 }, style:{ fill:delta>=0?C.teal:C.red } },
        { type:'text', x:p2[0]+18, y:p2[1]-10, style:{ text:`${delta>=0?'+':''}${delta.toFixed(2)} pp`, fill:delta>=0?C.teal:C.red, font:`600 15px ${font}` } },
      ]};
    },
  }],
  graphic:[
    { type:'circle', left:180, top:91, shape:{ r:7 }, style:{ fill:'#FFFFFF', stroke:C.gray, lineWidth:2 } },
    { type:'text', left:195, top:83, style:{ text:'首版', fill:C.gray, font:`14px ${font}` } },
    { type:'circle', left:265, top:91, shape:{ r:7 }, style:{ fill:C.teal } },
    { type:'text', left:280, top:83, style:{ text:'末版', fill:C.gray, font:`14px ${font}` } },
  ],
}, 1280, 720);

console.log('Rendered five ECharts SVG figures to', figureDir);
