"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const collapse = require("../BertScript/assets/17.jaal_structural_collapse.js");
const {apply} = require("../BertScript/assets/16.jaal_visible_labels.js");

function fixture(spec) {
  const nodes = spec.nodes.map(id => ({id, label:id, title:id,
    color:"#abcdef", size:7, depth:2}));
  const edges = spec.edges.map(([from,to],i) =>
    ({id:"edge-"+i,from,to,color:"#91baff"}));
  const listeners = new Map();
  const makeSet = values => ({
    items:values.map(i=>({...i})),
    get(){return this.items.map(i=>({...i}));},
    getIds(){return this.items.map(i=>i.id);},
    remove(ids) {
      const gone=new Set(ids.map(String));
      this.items=this.items.filter(item=>!gone.has(String(item.id)));
    },
    update(changes){
      for(const update of changes){
        const target=this.items.find(item=>item.id===update.id);
        if(target) Object.assign(target,update);
        else this.items.push({...update});
      }
    }
  });
  const fitCalls=[];
  const component={
    nn:makeSet(nodes),ee:makeSet(edges),props:{data:{nodes,edges}},
    net:{
      on(event,fn){assert.equal(event,"click");listeners.set(event,fn);},
      fit(options){fitCalls.push(options);}
    }
  };
  function run(mode){
    const command=apply(mode,component.props.data);
    assert.ok(command);
    new Function(command).call(component);
  }
  return {component,nodes,edges,fitCalls,run,click:id=>{
    assert.ok(listeners.has("click"));
    listeners.get("click")({nodes:[id]});
  }};
}

test("graph DAG unique descendant count does not double-count multiple parents",()=>{
  const m=collapse.graphModel({nodes:["A","B","C","D"].map(id=>({id})),
    edges:[["A","B"],["A","C"],["B","D"],["C","D"]].map(([from,to])=>({from,to}))});
  assert.equal(m.uniqueDescendants("A"),3);
  assert.equal(m.uniqueDescendants("B"),1);
  assert.equal(m.uniqueDescendants("C"),1);
  assert.equal(m.uniqueDescendants("D"),0);
  assert.deepEqual([...m.roots],["A"]);
});

test("cycle-safe unique counts and disconnected root fallback are bounded",()=>{
  const model=collapse.graphModel({
    nodes:["A","B","C","X","Y"].map(id=>({id})),
    edges:[["A","B"],["B","C"],["C","A"],["X","Y"]].map(([from,to])=>({from,to}))
  });
  assert.equal(model.uniqueDescendants("A"),2);
  assert.equal(model.uniqueDescendants("B"),2);
  assert.equal(model.uniqueDescendants("X"),1);
  assert.deepEqual(model.roots,["X","A"]);
});

test("both collapsed layouts preserve one original node each, label plus count only",()=>{
  for(const mode of ["hierarchical-collapsed","network-collapsed"]){
    const f=fixture({nodes:["A","B","C","D"],
      edges:[["A","B"],["A","C"],["B","D"],["C","D"]]});
    f.run(mode);
    let n=f.component.nn.get();
    assert.equal(n.length,mode==="hierarchical-collapsed"?3:4);
    if(mode==="hierarchical-collapsed"){
      assert.deepEqual(f.component.nn.getIds(),["A","B","C"]);
      assert.equal(f.component.ee.getIds().length,2);
      assert.deepEqual(f.fitCalls.at(-1).nodes,["A","B","C"]);
      assert.equal(f.fitCalls.length,1,"only initial collapsed entry fits");
    }
    assert.equal(n.find(x=>x.id==="A").hidden,false);
    assert.equal(n.find(x=>x.id==="A").label,"A");
    assert.equal(n.find(x=>x.id==="B").label,"B\n1");
    assert.equal(n.find(x=>x.id==="C").label,"C\n1");
    if(mode==="hierarchical-collapsed") assert.equal(n.find(x=>x.id==="D"),undefined);
    else assert.equal(n.find(x=>x.id==="D").hidden,true);
    assert.equal(f.component.ee.get().filter(e=>!e.hidden).length,2);
    f.click("B");
    n=f.component.nn.get();
    assert.equal(n.find(x=>x.id==="D").hidden,false);
    assert.equal(n.find(x=>x.id==="B").label,"B");
    assert.equal(f.component.ee.get().filter(e=>!e.hidden).length,3); // C still collapsed
    f.click("B");
    if(mode==="hierarchical-collapsed")
      assert.equal(f.component.nn.get().find(x=>x.id==="D"),undefined);
    else assert.equal(f.component.nn.get().find(x=>x.id==="D").hidden,true);
    // Click root once: hide both branches; one bubble with 3 unique descendants.
    f.click("A");
    n=f.component.nn.get();
    assert.equal(n.find(x=>x.id==="A").label,"A\n3");
    assert.equal(n.filter(x=>!x.hidden).length,1);
    if(mode==="hierarchical-collapsed") {
      assert.deepEqual(f.component.nn.getIds(),["A"]);
      assert.equal(f.component.ee.getIds().length,0);
      assert.deepEqual(f.fitCalls.at(-1).nodes,["A","B","C"]);
      assert.equal(f.fitCalls.length,1,
        "collapsing a branch must not recenter the viewport");
    } else {
      assert.equal(n.find(x=>x.id==="B").color,"#abcdef");
      assert.equal(n.find(x=>x.id==="D").title,"D");
    }
  }
});

test("normal network and hierarchy restore source visibility, including Search hidden",()=>{
  const f=fixture({nodes:["A","B","C"],edges:[["A","B"],["B","C"]]});
  f.nodes[2].hidden=true; // Source of truth from upstream Jaal Search callback
  f.run("hierarchical-collapsed");
  assert.equal(f.component.nn.get().find(n=>n.id==="B").label,"B\n1");
  f.run("network");
  assert.equal(f.component.nn.get().find(n=>n.id==="C").hidden,true);
  assert.equal(f.component.nn.get().find(n=>n.id==="B").label,"B");
  assert.equal(f.component.nn.get().find(n=>n.id==="A").hidden,false);
  f.run("network-collapsed");
  f.run("hierarchical");
  assert.equal(f.component.nn.get().find(n=>n.id==="A").hidden,false);
  assert.equal(f.component.nn.get().find(n=>n.id==="C").hidden,true);
});

test("long labels remain bounded, leaves have no zero counter, no code interpolation",()=>{
  const name="CN Intelligence And Espionage Against TW";
  const f=fixture({nodes:["A",name],edges:[["A",name]]});
  f.run("hierarchical-collapsed");
  const label=f.component.nn.get().find(n=>n.id===name).label;
  assert.ok(label.includes("\n"));
  assert.ok(label.split("\n").length <= 3);
  assert.equal(f.component.nn.get().find(n=>n.id===name).title,name);
  const dangerous='X"); throw Error("unsafe"); //';
  const code=apply("network-collapsed",{nodes:[{id:dangerous}],edges:[]});
  assert.ok(!code.includes(dangerous));
});

test("multiple edges and self loops do not inflate unique descendants",()=>{
  const g=collapse.graphModel({
    nodes:["A","B"].map(id=>({id})),
    edges:[["A","B"],["A","B"],["A","A"]].map(([from,to])=>({from,to}))
  });
  assert.equal(g.uniqueDescendants("A"),1);
  assert.equal(g.uniqueDescendants("B"),0);
});

test("collapsed mode respects original Search/Filter hidden flags and restores",()=>{
  const f=fixture({nodes:["A","B","C"],edges:[["A","B"],["B","C"]]});
  f.nodes[1].hidden=true;
  f.run("network-collapsed");
  // C remains a visible Search match, so B must be temporarily revealed
  // as its otherwise-hidden ancestor while the search overlay is active.
  assert.equal(f.component.nn.get().find(n=>n.id==="B").hidden,false);
  f.click("A"); // Search overlay is authoritative; click does not toggle.
  f.run("hierarchical");
  assert.equal(f.component.nn.get().find(n=>n.id==="B").hidden,true);
  assert.equal(f.component.nn.get().find(n=>n.id==="C").hidden,false);
});

test("Search reveals a deep match and its ancestors, not sibling branches",()=>{
  const f=fixture({nodes:["A","B","C","S"], edges:[["A","B"],["B","C"],["A","S"]]});
  // The original Jaal search has already hidden all nonmatches.
  f.nodes.forEach(n=>{n.hidden=(n.id!=="C");});
  f.run("hierarchical-collapsed");
  const nodes=f.component.nn.get();
  assert.deepEqual(nodes.filter(n=>!n.hidden).map(n=>n.id),["A","B","C"]);
  assert.equal(nodes.find(n=>n.id==="A").label,"A");
  assert.equal(nodes.find(n=>n.id==="B").label,"B");
  assert.equal(nodes.find(n=>n.id==="S"),undefined);
  assert.equal(f.component.ee.get().filter(e=>!e.hidden).length,2);
  f.click("A"); // Search remains authoritative until cleared.
  assert.equal(f.component.nn.get().find(n=>n.id==="C").hidden,false);
  f.nodes.forEach(n=>{n.hidden=false;});
  f.run("hierarchical-collapsed");
  assert.equal(f.component.nn.get().find(n=>n.id==="C"),undefined);
  f.click("B");
  assert.equal(f.component.nn.get().find(n=>n.id==="C").hidden,false);
});

test("Search through two parents reveals one shared match without double count",()=>{
  const f=fixture({nodes:["A","B","C","D"],edges:[
    ["A","B"],["A","C"],["B","D"],["C","D"]]});
  f.nodes.forEach(n=>{n.hidden=n.id!=="D";});
  f.run("network-collapsed");
  assert.deepEqual(f.component.nn.get().filter(n=>!n.hidden).map(n=>n.id),
    ["A","B","C","D"]);
  assert.equal(f.component.ee.get().filter(e=>!e.hidden).length,4);
});


test("hierarchical collapse really removes hidden IDs and reflows after toggles",()=>{
  const f=fixture({nodes:["A","B","C","D","E"],
    edges:[["A","B"],["A","C"],["B","D"],["D","E"]]});
  f.run("hierarchical-collapsed");
  assert.deepEqual(f.component.nn.getIds(),["A","B","C"]);
  assert.equal(f.component.ee.getIds().length,2);
  assert.deepEqual(f.fitCalls.at(-1).nodes,["A","B","C"]);
  f.click("B");
  assert.deepEqual(new Set(f.component.nn.getIds()),new Set(["A","B","C","D"]));
  assert.deepEqual(f.fitCalls.at(-1).nodes,["A","B","C"]);
  assert.equal(f.fitCalls.length,1,
    "expanding must not automatically zoom/pan");
  assert.equal(f.component.ee.getIds().length,3);
  f.click("B");
  assert.deepEqual(new Set(f.component.nn.getIds()),new Set(["A","B","C"]));
  assert.equal(f.fitCalls.length,1,
    "collapsing must preserve user camera");
  f.run("network");
  assert.equal(f.component.nn.getIds().length,5);
  assert.equal(f.component.ee.getIds().length,4);
  assert.equal(f.component.nn.get().find(n=>n.id==="E").title,"E");
  assert.equal(f.component.nn.get().find(n=>n.id==="E").color,"#abcdef");
  assert.equal(f.component.nn.get().find(n=>n.id==="E").label,"E");
});

test("network collapse rehydrates full DataSets after compact hierarchy",()=>{
  const f=fixture({nodes:["A","B","C","D"],
    edges:[["A","B"],["B","C"],["C","D"]]});
  f.run("hierarchical-collapsed");
  assert.equal(f.component.nn.getIds().length,2);
  const oldFit=f.fitCalls.length;
  f.run("network-collapsed");
  assert.equal(f.component.nn.getIds().length,4);
  assert.equal(f.component.ee.getIds().length,3);
  assert.equal(f.fitCalls.length,oldFit,"network retains natural force layout");
  assert.equal(f.component.nn.get().find(n=>n.id==="D").hidden,true);
  f.click("B");
  assert.equal(f.component.nn.get().find(n=>n.id==="C").hidden,false);
});

test("hierarchy Search only lays out matching ancestors then restores filters",()=>{
  const f=fixture({nodes:["A","B","C","D"],
    edges:[["A","B"],["B","C"],["A","D"]]});
  f.nodes.forEach(n=>{n.hidden=n.id!=="C";});
  f.run("hierarchical-collapsed");
  assert.deepEqual(new Set(f.component.nn.getIds()),new Set(["A","B","C"]));
  assert.equal(f.component.ee.getIds().length,2);
  f.run("hierarchical");
  assert.equal(f.component.nn.getIds().length,4);
  assert.equal(f.component.nn.get().find(n=>n.id==="D").hidden,true);
  assert.equal(f.component.nn.get().find(n=>n.id==="C").hidden,false);
});

test("hierarchical expansion morphs old nodes from their on-screen coordinates",()=>{
  const f=fixture({nodes:["A","B","C","D"],edges:[["A","B"],["A","C"],["B","D"]]});
  f.run("hierarchical-collapsed");
  const current={
    A:{x:0,y:0},B:{x:-80,y:260},C:{x:100,y:260}
  };
  const target={
    A:{x:40,y:0},B:{x:-100,y:260},C:{x:170,y:260},D:{x:-90,y:520}
  };
  let positionsRead=0;
  const redraws=[];
  f.component.net.getPositions=()=>{
    positionsRead++;
    return JSON.parse(JSON.stringify(positionsRead===1?current:target));
  };
  f.component.net.body={nodes:current};
  f.component.net.moveNode=()=>{throw Error("moveNode triggers redundant redraws");};
  f.component.net.redraw=()=>{redraws.push(true);};
  const oldRaf=globalThis.requestAnimationFrame;
  const oldCancel=globalThis.cancelAnimationFrame;
  const clock=new Map();
  let seq=0;
  globalThis.requestAnimationFrame=fn=>{clock.set(++seq,fn);return seq;};
  globalThis.cancelAnimationFrame=id=>clock.delete(id);
  const tick=timestamp=>{
    const [id,fn]=clock.entries().next().value;
    clock.delete(id);
    fn(timestamp);
  };
  try {
    f.click("B");
    assert.equal(positionsRead,2);
    assert.deepEqual(current.A,{x:0,y:0},"visible root must not jump before paint");
    assert.deepEqual(current.C,{x:100,y:260},"existing sibling stays put");
    assert.deepEqual(current.D,{x:-80,y:260},"new child starts at visible parent");
    assert.equal(f.fitCalls.length,1,"no camera pan or zoom on expansion");
    assert.equal(clock.size,1);
    tick(100);
    assert.deepEqual(current.A,{x:0,y:0});
    tick(330);
    assert.ok(current.A.x>0&&current.A.x<40,"existing root eases to new location");
    assert.ok(current.D.y>260&&current.D.y<520,"new child separates continuously");
    tick(600);
    for (const id of Object.keys(target)) {
      assert.ok(Math.abs(current[id].x-target[id].x)<0.0001);
      assert.ok(Math.abs(current[id].y-target[id].y)<0.0001);
    }
    assert.equal(clock.size,0);
    assert.ok(redraws.length>=2);
  } finally {
    if (oldRaf===undefined) delete globalThis.requestAnimationFrame;
    else globalThis.requestAnimationFrame=oldRaf;
    if (oldCancel===undefined) delete globalThis.cancelAnimationFrame;
    else globalThis.cancelAnimationFrame=oldCancel;
  }
});

test("leaving hierarchy cancels in-flight morph and restores original data",()=>{
  const f=fixture({nodes:["A","B","C"],edges:[["A","B"],["B","C"]]});
  f.run("hierarchical-collapsed");
  let reads=0;
  const positions={A:{x:0,y:0},B:{x:0,y:260},C:{x:0,y:520}};
  f.component.net.getPositions=()=>JSON.parse(JSON.stringify(
    ++reads===1?{A:positions.A,B:positions.B}:positions));
  const redraws=[];
  f.component.net.body={nodes:{
    A:{x:0,y:0},B:{x:0,y:260},C:{x:0,y:520}
  }};
  f.component.net.moveNode=()=>{throw Error("per-node canvas redraw prohibited");};
  f.component.net.redraw=()=>redraws.push(true);
  const oldRaf=globalThis.requestAnimationFrame;
  const oldCancel=globalThis.cancelAnimationFrame;
  const frames=new Map();let next=0;
  globalThis.requestAnimationFrame=fn=>{frames.set(++next,fn);return next;};
  globalThis.cancelAnimationFrame=id=>frames.delete(id);
  try {
    f.click("B");
    assert.equal(frames.size,1);
    const inFlight=[...frames.values()][0];
    f.run("network");
    assert.equal(frames.size,0,"old animation callback is canceled");
    const count=redraws.length;
    inFlight(500);
    assert.equal(redraws.length,count,"stale frame cannot move normal network nodes");
    assert.deepEqual(f.component.nn.getIds(),["A","B","C"]);
    assert.equal(f.fitCalls.length,1);
  } finally {
    if (oldRaf===undefined) delete globalThis.requestAnimationFrame;
    else globalThis.requestAnimationFrame=oldRaf;
    if (oldCancel===undefined) delete globalThis.cancelAnimationFrame;
    else globalThis.cancelAnimationFrame=oldCancel;
  }
});

test("reduced-motion users keep native hierarchy without animation",()=>{
  const f=fixture({nodes:["A","B","C"],edges:[["A","B"],["B","C"]]});
  f.run("hierarchical-collapsed");
  f.component.net.getPositions=()=>({A:{x:0,y:0},B:{x:20,y:260},C:{x:20,y:520}});
  let moves=0;
  f.component.net.moveNode=()=>moves++;
  const oldRaf=globalThis.requestAnimationFrame;
  const oldMedia=globalThis.matchMedia;
  globalThis.requestAnimationFrame=()=>{throw Error("must not animate");};
  globalThis.matchMedia=()=>({matches:true});
  try {
    f.click("B");
    assert.equal(moves,0);
    assert.equal(f.component.nn.getIds().length,3);
  } finally {
    if (oldRaf===undefined) delete globalThis.requestAnimationFrame;
    else globalThis.requestAnimationFrame=oldRaf;
    if (oldMedia===undefined) delete globalThis.matchMedia;
    else globalThis.matchMedia=oldMedia;
  }
});

test("large hierarchical reflow requests only one canvas redraw per frame",()=>{
  const siblings=Array.from({length:76},(_,i)=>"child-"+i);
  const ids=["root",...siblings,"grandchild"];
  const f=fixture({nodes:ids,edges:[
    ...siblings.map(id=>["root",id]),["child-0","grandchild"]
  ]});
  f.run("hierarchical-collapsed");
  assert.equal(f.component.nn.getIds().length,77);
  const initial=Object.fromEntries(["root",...siblings].map((id,i)=>
    [id,{x:i*30,y:i===0?0:260}]));
  const ideal=Object.fromEntries(ids.map((id,i)=>
    [id,{x:i*30+25,y:id==="grandchild"?520:i===0?0:260}]));
  f.component.net.body={nodes:Object.fromEntries(ids.map(id=>
    [id,{...(initial[id]||ideal[id])}]))};
  let reads=0, redraws=0, queued=[];
  f.component.net.getPositions=()=>JSON.parse(JSON.stringify(
    ++reads===1?initial:ideal));
  f.component.net.moveNode=()=>{throw Error("per-node redraw must not run");};
  f.component.net.redraw=()=>{redraws++;};
  const oldRaf=globalThis.requestAnimationFrame;
  const oldCancel=globalThis.cancelAnimationFrame;
  globalThis.requestAnimationFrame=fn=>{queued.push(fn);return queued.length;};
  globalThis.cancelAnimationFrame=()=>{};
  try {
    f.click("child-0");
    assert.equal(redraws,1,"77 existing nodes still require only one redraw");
    assert.equal(f.fitCalls.length,1);
    for (const stamp of [0,230,460]) {
      const cb=queued.shift();
      assert.ok(cb,"frame was scheduled");
      cb(stamp);
    }
    assert.equal(redraws,4,"one init frame plus three animation frames");
  } finally {
    if (oldRaf===undefined) delete globalThis.requestAnimationFrame;
    else globalThis.requestAnimationFrame=oldRaf;
    if (oldCancel===undefined) delete globalThis.cancelAnimationFrame;
    else globalThis.cancelAnimationFrame=oldCancel;
  }
});
