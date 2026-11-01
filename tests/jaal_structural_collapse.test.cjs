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
    update(changes){
      for(const update of changes){
        const target=this.items.find(item=>item.id===update.id);
        assert.ok(target,"node and edge ID must remain unchanged");
        Object.assign(target,update);
      }
    }
  });
  const component={
    nn:makeSet(nodes),ee:makeSet(edges),props:{data:{nodes,edges}},
    net:{on(event,fn){assert.equal(event,"click");listeners.set(event,fn);}}
  };
  function run(mode){
    const command=apply(mode,component.props.data);
    assert.ok(command);
    new Function(command).call(component);
  }
  return {component,nodes,edges,run,click:id=>{
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
    assert.equal(n.length,4);
    assert.equal(n.find(x=>x.id==="A").hidden,false);
    assert.equal(n.find(x=>x.id==="A").label,"A");
    assert.equal(n.find(x=>x.id==="B").label,"B\n1");
    assert.equal(n.find(x=>x.id==="C").label,"C\n1");
    assert.equal(n.find(x=>x.id==="D").hidden,true);
    assert.equal(f.component.ee.get().filter(e=>!e.hidden).length,2);
    f.click("B");
    n=f.component.nn.get();
    assert.equal(n.find(x=>x.id==="D").hidden,false);
    assert.equal(n.find(x=>x.id==="B").label,"B");
    assert.equal(f.component.ee.get().filter(e=>!e.hidden).length,3); // C still collapsed
    f.click("B");
    assert.equal(f.component.nn.get().find(x=>x.id==="D").hidden,true);
    // Click root once: hide both branches; one bubble with 3 unique descendants.
    f.click("A");
    n=f.component.nn.get();
    assert.equal(n.find(x=>x.id==="A").label,"A\n3");
    assert.equal(n.filter(x=>!x.hidden).length,1);
    assert.equal(n.find(x=>x.id==="B").color,"#abcdef");
    assert.equal(n.find(x=>x.id==="D").title,"D");
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
  assert.equal(f.component.nn.get().find(n=>n.id==="B").hidden,true);
  f.click("A"); // Collapse the root.
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
  assert.equal(nodes.find(n=>n.id==="S").hidden,true);
  assert.equal(f.component.ee.get().filter(e=>!e.hidden).length,2);
  f.click("A"); // Search remains authoritative until cleared.
  assert.equal(f.component.nn.get().find(n=>n.id==="C").hidden,false);
  f.nodes.forEach(n=>{n.hidden=false;});
  f.run("hierarchical-collapsed");
  assert.equal(f.component.nn.get().find(n=>n.id==="C").hidden,true);
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
