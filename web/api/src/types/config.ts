import { z } from 'zod';

export const AppConfigSchema = z.object({
  kbRoot: z.string().optional(),
});

export interface AppConfig {
  kbRoot?: string;
}
