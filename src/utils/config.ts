import * as fs from 'fs-extra';
import * as path from 'path';
import { BackupConfig } from '../types';

export async function loadConfig(configPath: string): Promise<BackupConfig> {
  const absolutePath = path.resolve(process.cwd(), configPath);
  
  if (!await fs.pathExists(absolutePath)) {
    throw new Error(`配置文件不存在: ${absolutePath}`);
  }

  const config = await fs.readJson(absolutePath) as BackupConfig;
  await validateConfig(config);
  
  return config;
}

export async function validateConfig(config: BackupConfig): Promise<void> {
  if (!config.sourceDirs || !Array.isArray(config.sourceDirs) || config.sourceDirs.length === 0) {
    throw new Error('sourceDirs 必须是非空数组');
  }

  if (!config.targetDir || typeof config.targetDir !== 'string') {
    throw new Error('targetDir 必须是字符串');
  }

  if (config.strategy !== 'full' && config.strategy !== 'incremental') {
    throw new Error('strategy 必须是 "full" 或 "incremental"');
  }

  if (typeof config.retentionCount !== 'number' || config.retentionCount < 1) {
    throw new Error('retentionCount 必须是大于等于 1 的数字');
  }

  if (!config.cronExpression || typeof config.cronExpression !== 'string') {
    throw new Error('cronExpression 必须是字符串');
  }

  if (!Array.isArray(config.excludePatterns)) {
    throw new Error('excludePatterns 必须是数组');
  }

  for (const sourceDir of config.sourceDirs) {
    const absolutePath = path.resolve(process.cwd(), sourceDir);
    if (!await fs.pathExists(absolutePath)) {
      throw new Error(`源目录不存在: ${absolutePath}`);
    }
    const stat = await fs.stat(absolutePath);
    if (!stat.isDirectory()) {
      throw new Error(`源路径不是目录: ${absolutePath}`);
    }
  }
}
