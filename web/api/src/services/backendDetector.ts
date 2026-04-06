/**
 * Detects the configured LLM backend (claude-cli or opencode) from adjutant.yaml.
 *
 * Reads llm.backend, llm.models, and llm.permission_mode from the Adjutant
 * config. Finds the CLI binary via env var or PATH lookup.
 *
 * Results are cached — stale reads are acceptable since backend config
 * changes rarely and require a server restart to take effect.
 */

import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';
import { registryService } from './registryService.js';
import type { CliBackendInfo, CliBackendName } from '../types/session.js';

interface AdjutantYamlLlm {
  backend?: string;
  permission_mode?: string;
  models?: {
    cheap?: string;
    medium?: string;
    expensive?: string;
  };
}

interface AdjutantYaml {
  llm?: AdjutantYamlLlm;
}

let cachedResult: CliBackendInfo | null | undefined;

function findBinary(name: string, envVar: string): string | null {
  const envBin = process.env[envVar];
  if (envBin) {
    try {
      fs.accessSync(envBin, fs.constants.X_OK);
      return envBin;
    } catch {
      return null;
    }
  }

  try {
    const result = execSync(`which ${name}`, { encoding: 'utf-8', timeout: 5000 }).trim();
    return result || null;
  } catch {
    return null;
  }
}

export async function detect(): Promise<CliBackendInfo | null> {
  if (cachedResult !== undefined) return cachedResult;

  const adjDir = await registryService.resolveAdjutantDir();
  if (!adjDir) {
    cachedResult = null;
    return null;
  }

  const yamlPath = path.join(adjDir, 'adjutant.yaml');
  let yamlContent: string;
  try {
    yamlContent = fs.readFileSync(yamlPath, 'utf-8');
  } catch {
    cachedResult = null;
    return null;
  }

  let config: AdjutantYaml;
  try {
    config = yaml.load(yamlContent) as AdjutantYaml;
  } catch {
    cachedResult = null;
    return null;
  }

  const llm = config?.llm;
  if (!llm?.backend) {
    cachedResult = null;
    return null;
  }

  const backendName = llm.backend as CliBackendName;
  if (backendName !== 'claude-cli' && backendName !== 'opencode') {
    cachedResult = null;
    return null;
  }

  // Find the binary
  let binary: string | null;
  if (backendName === 'claude-cli') {
    binary = findBinary('claude', 'CLAUDE_CODE_BIN');
  } else {
    binary = findBinary('opencode', 'OPENCODE_BIN');
  }

  if (!binary) {
    cachedResult = null;
    return null;
  }

  cachedResult = {
    name: backendName,
    binary,
    permissionMode: llm.permission_mode || 'skip',
    models: {
      cheap: llm.models?.cheap || 'anthropic/claude-haiku-4-5',
      medium: llm.models?.medium || 'anthropic/claude-sonnet-4-6',
      expensive: llm.models?.expensive || 'anthropic/claude-opus-4-6',
    },
  };

  return cachedResult;
}

export function clearCache(): void {
  cachedResult = undefined;
}

export const backendDetector = { detect, clearCache };
