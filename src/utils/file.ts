import * as fs from 'fs-extra';
import * as path from 'path';
import { BackupInfo } from '../types';

const BACKUP_NAME_REGEX = /^backup_(\d{13})_(full|incremental)$/;

function parseBackupType(raw: string): 'full' | 'incremental' | null {
  if (raw === 'full' || raw === 'incremental') return raw;
  return null;
}

export function shouldExclude(filePath: string, excludePatterns: string[]): boolean {
  const basename = path.basename(filePath);
  return excludePatterns.some(pattern => {
    const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.');
    const regex = new RegExp(`^${escaped}$`);
    return regex.test(basename);
  });
}

export async function getFileStats(dirPath: string, excludePatterns: string[] = []): Promise<{ files: string[]; totalSize: number }> {
  const files: string[] = [];
  let totalSize = 0;

  async function scan(currentPath: string) {
    const entries = await fs.readdir(currentPath, { withFileTypes: true });
    
    for (const entry of entries) {
      const fullPath = path.join(currentPath, entry.name);
      
      if (shouldExclude(fullPath, excludePatterns)) {
        continue;
      }

      if (entry.isDirectory()) {
        await scan(fullPath);
      } else if (entry.isFile()) {
        const stat = await fs.stat(fullPath);
        files.push(fullPath);
        totalSize += stat.size;
      }
    }
  }

  await scan(dirPath);
  return { files, totalSize };
}

export async function copyFileWithStats(
  source: string,
  target: string
): Promise<{ success: boolean; error?: string }> {
  try {
    await fs.ensureDir(path.dirname(target));
    await fs.copy(source, target, { preserveTimestamps: true });
    return { success: true };
  } catch (error) {
    return { success: false, error: (error as Error).message };
  }
}

export async function getLastBackupTime(targetDir: string): Promise<Date | null> {
  if (!await fs.pathExists(targetDir)) {
    return null;
  }

  const backups = await getBackupList(targetDir);
  if (backups.length === 0) {
    return null;
  }

  return backups[0].timestamp;
}

export async function getBackupList(targetDir: string): Promise<BackupInfo[]> {
  if (!await fs.pathExists(targetDir)) {
    return [];
  }

  const entries = await fs.readdir(targetDir, { withFileTypes: true });
  const backups: BackupInfo[] = [];

  for (const entry of entries) {
    const match = BACKUP_NAME_REGEX.exec(entry.name);
    if (entry.isDirectory() && match) {
      const backupPath = path.join(targetDir, entry.name);
      const reportPath = path.join(backupPath, 'report.json');
      
      if (await fs.pathExists(reportPath)) {
        try {
          const report = await fs.readJson(reportPath);
          const reportType = parseBackupType(report.type);
          backups.push({
            name: entry.name,
            timestamp: new Date(report.startTime),
            type: reportType || match[2] as 'full' | 'incremental',
            size: report.totalSize,
            fileCount: report.fileCount
          });
        } catch {
          const stat = await fs.stat(backupPath);
          backups.push({
            name: entry.name,
            timestamp: match[1] ? new Date(parseInt(match[1])) : stat.birthtime,
            type: match[2] as 'full' | 'incremental',
            size: 0,
            fileCount: 0
          });
        }
      }
    }
  }

  return backups.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(2)} 秒`;
  return `${(ms / 60000).toFixed(2)} 分钟`;
}
