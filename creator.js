'use strict';
const SUPABASE_URL='https://ozshekxpuvganemaajms.supabase.co';
const client=supabase.createClient(SUPABASE_URL,'sb_publishable__GsW9RahFD_XDWJTFzh9eQ_dNBZfa32');
const $=id=>document.getElementById(id);
let currentUser=null,selectedVideo=null,selectedThumbnail=null,busy=false;
let series=[],episodes=[],videoPreviewUrl=null,coverPreviewUrl=null;
function showStatus(text){$('status').textContent=text;$('status').style.display='block';}
function goToAIStudio(){location.href='ai-series-studio.html';}
function showUpload(){$('uploadSection').scrollIntoView({behavior:'smooth'});}
function scrollToEpisodes(){$('episodeSection').scrollIntoView({behavior:'smooth'});}
function safeName(name){return name.toLowerCase().replace(/[^a-z0-9.\-_]/g,'-').slice(-120);}
function validateFile(file,kind){
 const types=kind==='video'?['video/mp4','video/webm']:['image/jpeg','image/png','image/webp'];
 const max=(kind==='video'?50:5)*1024*1024;
 if(!file || !types.includes(file.type))throw new Error(kind==='video'?'Choose an MP4 or WebM video.':'Choose a JPG, PNG or WebP cover.');
 if(file.size===0 || file.size>max)throw new Error(`${kind==='video'?'Video':'Cover'} must be between 1 byte and ${max/1024/1024} MB.`);
}
function resetFiles(){
 selectedVideo=null;selectedThumbnail=null;
 $('videoInput').value='';$('thumbnailInput').value='';
 $('videoPreview').removeAttribute('src');$('videoPreview').load();
 $('thumbnailPreview').removeAttribute('src');$('thumbnailPreview').style.display='none';$('previewBox').style.display='none';
 if(videoPreviewUrl)URL.revokeObjectURL(videoPreviewUrl);if(coverPreviewUrl)URL.revokeObjectURL(coverPreviewUrl);
 videoPreviewUrl=coverPreviewUrl=null;
 $('videoFileName').textContent='MP4 or WebM · maximum 50 MB';$('thumbnailFileName').textContent='JPG, PNG or WebP · maximum 5 MB';
}
$('videoInput').addEventListener('change',event=>{
 selectedVideo=null;
 try{const file=event.target.files[0];validateFile(file,'video');selectedVideo=file;
 if(videoPreviewUrl)URL.revokeObjectURL(videoPreviewUrl);videoPreviewUrl=URL.createObjectURL(file);
 $('videoPreview').src=videoPreviewUrl;$('previewBox').style.display='block';$('videoFileName').textContent=file.name;
 }catch(error){event.target.value='';$('previewBox').style.display='none';showStatus(error.message);}
});
$('thumbnailInput').addEventListener('change',event=>{
 selectedThumbnail=null;
 try{const file=event.target.files[0];validateFile(file,'cover');selectedThumbnail=file;
 if(coverPreviewUrl)URL.revokeObjectURL(coverPreviewUrl);coverPreviewUrl=URL.createObjectURL(file);
 $('thumbnailPreview').src=coverPreviewUrl;$('thumbnailPreview').style.display='block';$('thumbnailFileName').textContent=file.name;
 }catch(error){event.target.value='';$('thumbnailPreview').style.display='none';showStatus(error.message);}
});
function chooseSeries(){
 const item=series.find(s=>s.drama_id===$('seriesSelect').value);
 $('seriesTitle').readOnly=!!item;$('seriesTitle').value=item?.title||'';
 const numbers=episodes.filter(e=>e.drama_id===item?.drama_id).map(e=>Number(e.episode_number));
 $('episodeNumber').value=numbers.length?Math.max(...numbers)+1:1;
}
$('seriesSelect').addEventListener('change',chooseSeries);
async function loadSeries(){
 const result=await client.from('creator_series').select('drama_id,title,created_at').eq('creator_id',currentUser.id).order('created_at',{ascending:false});
 if(result.error)throw result.error;series=result.data||[];
 const selected=$('seriesSelect').value;
 $('seriesSelect').replaceChildren(new Option('Start a new series',''));
 series.forEach(item=>$('seriesSelect').append(new Option(item.title,item.drama_id)));
 if(series.some(s=>s.drama_id===selected))$('seriesSelect').value=selected;
 const month=new Date().toISOString().slice(0,7),used=series.filter(s=>s.created_at.slice(0,7)===month).length;
 $('quotaInfo').textContent=used?'Your new-series allowance is used for this month. You can add episodes to an existing series.':'You can start one new drama series this month.';
}
async function loadEpisodes(){
 const result=await client.from('episodes').select('id,drama_id,series_title,episode_title,episode_number,genre,video_url,is_published,review_status,review_note,coin_cost').eq('creator_id',currentUser.id).order('created_at',{ascending:false});
 if(result.error)throw result.error;episodes=result.data||[];
 const list=$('episodeList');list.replaceChildren();
 if(!episodes.length){list.textContent='Your uploaded episodes will appear here.';return;}
 for(const ep of episodes){
  const card=document.createElement('article');card.className='episode-card';
  const title=document.createElement('h3');title.className='episode-title';title.textContent=`${ep.series_title} · Episode ${ep.episode_number}`;
  const info=document.createElement('p');info.className='episode-info';info.textContent=`${ep.episode_title} · ${ep.is_published?'Published':ep.review_status==='rejected'?'Needs changes':'Awaiting review'} · ${ep.coin_cost||0} coins`;
  card.append(title,info);
  if(ep.review_note){const note=document.createElement('p');note.textContent=ep.review_note;card.append(note);}
  const preview=document.createElement('button');preview.className='primary-btn';preview.textContent='Preview my upload';
  preview.onclick=async()=>{
   preview.disabled=true;
   try{
    const url=new URL(ep.video_url),prefix='/storage/v1/object/public/zynora-videos/';
    if(url.origin!==SUPABASE_URL || !url.pathname.startsWith(prefix))throw new Error('Preview is unavailable for this legacy video.');
    const signed=await client.storage.from('zynora-videos').createSignedUrl(decodeURIComponent(url.pathname.slice(prefix.length)),600);
    if(signed.error)throw signed.error;
    let player=card.querySelector('video');if(!player){player=document.createElement('video');player.controls=true;player.style.width='100%';card.append(player);}
    player.src=signed.data.signedUrl;player.load();
   }catch(error){showStatus(error.message);}finally{preview.disabled=false;}
  };
  card.append(preview);
  const edit=document.createElement('button');edit.className='primary-btn';edit.textContent='Edit episode title';
  edit.onclick=async()=>{
   const title=prompt('Episode title (editing sends the episode for review again):',ep.episode_title);
   if(title===null)return;if(!title.trim()||title.trim().length>150){showStatus('Use a title of 1–150 characters.');return;}
   edit.disabled=true;
   try{const saved=await client.from('episodes').update({episode_title:title.trim()}).eq('id',ep.id).eq('creator_id',currentUser.id).select('id').single();if(saved.error)throw saved.error;await loadEpisodes();showStatus('Changes saved and submitted for review.');}catch(error){showStatus(error.message);edit.disabled=false;}
  };
  card.append(edit);list.append(card);
 }
}
async function loadEarnings(){
 const result=await client.from('creator_earnings').select('creator_usd,paid_coins,net_revenue_usd').eq('creator_id',currentUser.id);
 if(result.error){$('earningsSummary').textContent='Earnings are temporarily unavailable.';return;}
 const rows=result.data||[],total=rows.reduce((sum,row)=>sum+Number(row.creator_usd||0),0),pending=rows.filter(row=>row.net_revenue_usd===null).length;
 $('earningsSummary').textContent=`Estimated creator earnings: $${total.toFixed(2)} USD${pending?' · '+pending+' payment allocation(s) awaiting fee reconciliation':''}. Your share: 80%.`;
}
async function publishEpisode(){
 if(busy)return;
 if(!currentUser){showStatus('Sign in with your own Zynora account to upload.');return;}
 const episodeTitle=$('episodeTitle').value.trim(),seriesTitle=$('seriesTitle').value.trim();
 const episodeNumber=Number($('episodeNumber').value),coinCost=Number($('coinCost').value);
 let dramaId=$('seriesSelect').value;
 const uploaded=[];let attemptedSave=false;const episodeId=crypto.randomUUID();
 try{
  if(!seriesTitle||seriesTitle.length>150||!episodeTitle||episodeTitle.length>150)throw new Error('Enter a series and episode title of 1–150 characters.');
  if(!Number.isSafeInteger(episodeNumber)||episodeNumber<1||episodeNumber>100000)throw new Error('Enter a valid whole episode number.');
  if(!Number.isSafeInteger(coinCost)||coinCost<0||coinCost>10000)throw new Error('Choose a whole coin cost from 0 to 10,000.');
  if(!$('rightsConfirmed').checked)throw new Error('Confirm that you have permission to publish this content.');
  validateFile(selectedVideo,'video');if(selectedThumbnail)validateFile(selectedThumbnail,'cover');
  if(!dramaId&&series.some(s=>s.created_at.slice(0,7)===new Date().toISOString().slice(0,7)))throw new Error('Choose an existing series. Your new-series allowance is used for this month.');
  if(dramaId&&episodes.some(e=>e.drama_id===dramaId&&Number(e.episode_number)===episodeNumber))throw new Error('That episode number already exists in this series.');
  busy=true;$('publishBtn').disabled=true;$('publishBtn').textContent='Uploading…';
  const auth=await client.auth.getUser();if(auth.error||auth.data.user?.id!==currentUser.id)throw new Error('Your session changed. Sign in again before uploading.');
  dramaId=dramaId||'creator-'+crypto.randomUUID();
  async function upload(bucket,file){
   const path=`${currentUser.id}/${episodeId}-${safeName(file.name)}`;
   const result=await client.storage.from(bucket).upload(path,file,{upsert:false,contentType:file.type});if(result.error)throw result.error;
   uploaded.push({bucket,path});return client.storage.from(bucket).getPublicUrl(path).data.publicUrl;
  }
  showStatus('Uploading video. Keep this page open until submission finishes.');
  const videoUrl=await upload('zynora-videos',selectedVideo);
  let thumbnailUrl=null;if(selectedThumbnail){showStatus('Uploading cover…');thumbnailUrl=await upload('zynora-thumbnails',selectedThumbnail);}
  showStatus('Submitting your episode for review…');attemptedSave=true;
  const saved=await client.from('episodes').insert({id:episodeId,drama_id:dramaId,series_title:seriesTitle,drama_title:seriesTitle,episode_title:episodeTitle,episode_number:episodeNumber,coin_cost:coinCost,description:$('description').value.trim(),genre:$('genre').value,video_url:videoUrl,thumbnail_url:thumbnailUrl}).select('id').single();
  if(saved.error)throw saved.error;
  resetFiles();$('episodeTitle').value='';$('rightsConfirmed').checked=false;
  await loadEpisodes();await loadSeries();$('seriesSelect').value=dramaId;chooseSeries();
  showStatus('Episode submitted. It will appear in Zynora after approval.');
 }catch(error){
  let canClean=!attemptedSave;
  if(attemptedSave){const check=await client.from('episodes').select('id').eq('id',episodeId).maybeSingle();canClean=!check.error&&!check.data;if(check.data){showStatus('Your episode was saved. Refresh to see its review status.');return;}}
  if(canClean)await Promise.allSettled(uploaded.map(item=>client.storage.from(item.bucket).remove([item.path])));
  showStatus(error.message||'Upload failed. Please try again.');
 }finally{busy=false;$('publishBtn').disabled=!currentUser;$('publishBtn').textContent='Submit for Review';}
}
async function startCreator(){
 $('publishBtn').disabled=true;
 try{const result=await client.auth.getUser();
 if(result.error||!result.data.user){$('episodeList').textContent='Sign in to view your episodes.';return;}
 currentUser=result.data.user;$('authLinks').hidden=true;
 await loadEpisodes();await loadSeries();await loadEarnings();$('publishBtn').disabled=false;
 showStatus('You are using your own creator account. Your uploads and earnings belong to this account.');
 }catch(error){showStatus('Creator Studio could not load: '+error.message);}
}
client.auth.onAuthStateChange(event=>{if(event==='SIGNED_OUT'){currentUser=null;$('publishBtn').disabled=true;resetFiles();$('episodeList').replaceChildren();$('earningsSummary').textContent='Sign in to view earnings.';$('authLinks').hidden=false;}});
window.addEventListener('beforeunload',event=>{if(busy){event.preventDefault();event.returnValue='';}});
startCreator();
