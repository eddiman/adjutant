import path from 'path';
import os from 'os';

export const config = {
  port: parseInt(process.env.ADJUTANT_WEB_PORT || '3020'),
  host: process.env.ADJUTANT_WEB_HOST || '0.0.0.0',
  configDir: path.join(os.homedir(), '.adjutant-web'),
  get configFile() {
    return path.join(this.configDir, 'config.json');
  },
};
