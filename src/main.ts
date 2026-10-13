// App entry. During M0 the app is the style-frame viewer (SPEC §T.19). The template's
// Havok physics demo is retired; Havok returns with character controllers.
import { startStyleViewer } from './style/viewer';

const canvas = document.getElementById('renderCanvas') as HTMLCanvasElement;
startStyleViewer(canvas).catch((err) => {
  console.error(err);
  document.body.insertAdjacentHTML('beforeend', `<pre style="color:#c33;position:fixed;top:0;left:0">${String(err)}</pre>`);
});
