// Usage: node test/global.mjs [base_url]  (checks include_global on search_trials/search_papers; default output unchanged)
const base=(process.argv[2]||"http://127.0.0.1:8787")+"/mcp";
const call=async(name,args)=>{const r=await fetch(base,{method:"POST",headers:{"content-type":"application/json",accept:"application/json"},body:JSON.stringify({jsonrpc:"2.0",id:1,method:"tools/call",params:{name,arguments:args}})});return (await r.json()).result};
const tl=await (await fetch(base,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({jsonrpc:"2.0",id:1,method:"tools/list"})})).json();
for(const t of tl.result.tools.filter(t=>/search_(trials|papers)/.test(t.name))) console.log(t.name,"| include_global:",JSON.stringify(t.inputSchema.properties.include_global),"\n  desc:",t.description.slice(0,120));
const a=await call("search_trials",{intervention:"semaglutide",max_records:2});console.log("default trials isArray:",Array.isArray(a.structuredContent.result));
const b=await call("search_trials",{condition:"obesity",intervention:"mazdutide",max_records:50,include_global:true});const r=b.structuredContent.result;console.log("global trials:",r.trials.length,"links:",r.trials.flatMap(t=>t.global_links).slice(0,2),"disclaimer:",!!r.global_disclaimer);
const b2=await call("search_trials",{condition:"Anesthesia",max_records:100,include_global:true});const r2=b2.structuredContent.result;console.log("anesthesia links:",JSON.stringify(r2.trials.flatMap(t=>t.global_links).slice(0,1)),"disclaimer:",!!r2.global_disclaimer);
const c=await call("search_papers",{keyword:"mazdutide",max_records:5,include_global:true});console.log(c.isError?c.content[0].text:JSON.stringify(c.structuredContent.result.papers.map(p=>[p.jurisdiction_flag,p.jurisdiction])), "disc:",!!c.structuredContent?.result?.global_disclaimer);
const d=await call("search_papers",{keyword:"mazdutide",max_records:2});console.log("default papers isArray:",Array.isArray(d.structuredContent.result));
