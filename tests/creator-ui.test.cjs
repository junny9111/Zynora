const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{value:'',style:{},textContent:'',addEventListener(){},replaceChildren(){},append(){},removeAttribute(){},load(){},scrollIntoView(){}});return nodes.get(id);}
const client={auth:{getUser:async()=>({data:{user:null},error:null}),onAuthStateChange(){} }};
const ctx=vm.createContext({console,document:{getElementById:node},supabase:{createClient:()=>client},window:{addEventListener(){}},location:{},URL,Option:function(){},crypto:require('node:crypto').webcrypto,setTimeout});
vm.runInContext(fs.readFileSync('creator.js','utf8'),ctx);
const check=code=>vm.runInContext(code,ctx);
assert.equal(check("validateFile({type:'video/mp4',size:50*1024*1024},'video')"),undefined);
assert.throws(()=>check("validateFile({type:'video/mp4',size:50*1024*1024+1},'video')"),/50 MB/);
assert.throws(()=>check("validateFile({type:'text/html',size:100},'video')"),/MP4/);
assert.throws(()=>check("validateFile({type:'image/svg+xml',size:100},'cover')"),/JPG/);
assert.throws(()=>check("validateFile({type:'video/mp4',size:0},'video')"),/1 byte/);
assert.equal(check("safeName('../../bad <script>.mp4').includes('<')"),false);
check('publishEpisode()').then(()=>{
 assert.equal(node('publishBtn').disabled,true);
 assert.match(node('status').textContent,/Sign in/);
 console.log('PASS: file limits, unsupported formats, empty files, filename sanitization, signed-out upload gating');
});
