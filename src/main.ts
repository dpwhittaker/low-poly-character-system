// App entry. M1: the creator preview (SPEC T22/T27) is the default page; the approved M0
// style frames stay reachable at ?app=m0. The template's Havok demo is retired; Havok
// returns with character controllers.
const canvas = document.getElementById('renderCanvas') as HTMLCanvasElement;
const app = new URLSearchParams(location.search).get('app');
const start = app === 'm0'
  ? import('./style/viewer').then((m) => m.startStyleViewer(canvas))
  : import('./creator/viewer').then((m) => m.startCreator(canvas));
start.catch((err) => {
  console.error(err);
  document.body.insertAdjacentHTML('beforeend', `<pre style="color:#c33;position:fixed;top:0;left:0">${String(err)}</pre>`);
});
