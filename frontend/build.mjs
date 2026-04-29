import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { buildProject } from './build-preset.mjs';
import project from './mutgui.build.mjs';

const frontendDir = dirname(fileURLToPath(import.meta.url));

await buildProject(frontendDir, project);
