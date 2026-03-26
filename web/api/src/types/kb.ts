import { z } from 'zod';

// kb.yaml schema (Adjutant standard)
export const KbYamlSchema = z.object({
  name: z.string(),
  description: z.string().default(''),
  model: z.string().optional(),
  access: z.enum(['read-only', 'read-write']).default('read-only'),
  created: z.string().optional(),
  // Allow additional fields from Adjutant (language, github, cli_module, etc.)
}).passthrough();

export interface KbMeta {
  name: string;
  description: string;
  path: string;
  access: 'read-only' | 'read-write';
  created?: string;
}
