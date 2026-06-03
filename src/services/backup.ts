import * as fs from 'fs-extra';
import * as path from 'path';
import { BackupConfig, BackupReport, BackupInfo } from '../types';
import { getFileStats, copyFileWithStats, getBackupList, getLastBackupTime } from '../utils/file';

interface BackupFileResult {
  successFiles: string[];
  failedFiles: { file: string; error: string }[];
  totalSize: number;
}

async function processBackupFiles(
  config: BackupConfig,
  backupPath: string,
  shouldCopy: (file: string, stat: fs.Stats) => boolean
): Promise<BackupFileResult> {
  const successFiles: string[] = [];
  const failedFiles: { file: string; error: string }[] = [];
  let totalSize = 0;

  for (const sourceDir of config.sourceDirs) {
    const absoluteSourceDir = path.resolve(process.cwd(), sourceDir);
    const { files } = await getFileStats(absoluteSourceDir, config.excludePatterns);

    for (const file of files) {
      const stat = await fs.stat(file);
      
      if (!shouldCopy(file, stat)) {
        continue;
      }

      const relativePath = path.relative(absoluteSourceDir, file);
      const targetPath = path.join(backupPath, path.basename(sourceDir), relativePath);
      
      const result = await copyFileWithStats(file, targetPath);
      
      if (result.success) {
        successFiles.push(file);
        totalSize += stat.size;
      } else {
        failedFiles.push({ file, error: result.error || '未知错误' });
      }
    }
  }

  return { successFiles, failedFiles, totalSize };
}

export async function performFullBackup(config: BackupConfig): Promise<BackupReport> {
  const startTime = new Date();
  const backupName = `backup_${startTime.getTime()}_full`;
  const backupPath = path.resolve(process.cwd(), config.targetDir, backupName);
  
  await fs.ensureDir(backupPath);

  const result = await processBackupFiles(config, backupPath, () => true);

  const endTime = new Date();
  const report: BackupReport = {
    backupName,
    type: 'full',
    startTime,
    endTime,
    duration: endTime.getTime() - startTime.getTime(),
    fileCount: result.successFiles.length,
    totalSize: result.totalSize,
    successFiles: result.successFiles,
    failedFiles: result.failedFiles
  };

  await fs.writeJson(path.join(backupPath, 'report.json'), report, { spaces: 2 });

  return report;
}

export async function performIncrementalBackup(config: BackupConfig): Promise<BackupReport> {
  const startTime = new Date();
  const backupName = `backup_${startTime.getTime()}_incremental`;
  const backupPath = path.resolve(process.cwd(), config.targetDir, backupName);
  
  await fs.ensureDir(backupPath);

  const lastBackupTime = await getLastBackupTime(path.resolve(process.cwd(), config.targetDir));

  const result = await processBackupFiles(
    config,
    backupPath,
    (_, stat) => !lastBackupTime || stat.mtime > lastBackupTime
  );

  const endTime = new Date();
  const report: BackupReport = {
    backupName,
    type: 'incremental',
    startTime,
    endTime,
    duration: endTime.getTime() - startTime.getTime(),
    fileCount: result.successFiles.length,
    totalSize: result.totalSize,
    successFiles: result.successFiles,
    failedFiles: result.failedFiles
  };

  await fs.writeJson(path.join(backupPath, 'report.json'), report, { spaces: 2 });

  return report;
}

export async function performBackup(config: BackupConfig): Promise<BackupReport> {
  if (config.strategy === 'full') {
    return performFullBackup(config);
  }
  return performIncrementalBackup(config);
}

export async function cleanupOldBackups(config: BackupConfig): Promise<string[]> {
  const targetDir = path.resolve(process.cwd(), config.targetDir);
  const backups = await getBackupList(targetDir);
  
  const toDelete = backups.slice(config.retentionCount);
  const deleted: string[] = [];

  for (const backup of toDelete) {
    const backupPath = path.join(targetDir, backup.name);
    await fs.remove(backupPath);
    deleted.push(backup.name);
  }

  return deleted;
}

function getBackupChain(targetBackup: BackupInfo, allBackups: BackupInfo[]): BackupInfo[] {
  const sortedAsc = [...allBackups].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());

  const targetIndex = sortedAsc.findIndex(b => b.name === targetBackup.name);
  if (targetIndex === -1) {
    return [targetBackup];
  }

  let fullBackupIndex = -1;
  for (let i = targetIndex; i >= 0; i--) {
    if (sortedAsc[i].type === 'full') {
      fullBackupIndex = i;
      break;
    }
  }

  if (fullBackupIndex === -1) {
    return [];
  }

  const chain: BackupInfo[] = [];
  for (let i = fullBackupIndex; i <= targetIndex; i++) {
    chain.push(sortedAsc[i]);
  }

  return chain;
}

export async function restoreBackup(backupName: string, config: BackupConfig): Promise<{ 
  success: boolean; 
  restoredFiles: string[]; 
  failedFiles: string[];
  backupChain: BackupInfo[];
}> {
  const targetDir = path.resolve(process.cwd(), config.targetDir);
  const allBackups = await getBackupList(targetDir);
  
  const targetBackup = allBackups.find(b => b.name === backupName);
  if (!targetBackup) {
    throw new Error(`备份不存在: ${backupName}`);
  }

  const backupChain = getBackupChain(targetBackup, allBackups);
  
  const earliestFullBackup = backupChain.find(b => b.type === 'full');
  if (!earliestFullBackup) {
    throw new Error('无法找到完整的备份链，缺少全量备份基础');
  }

  const restoredFiles: string[] = [];
  const failedFiles: string[] = [];

  for (const backup of backupChain) {
    const backupPath = path.join(targetDir, backup.name);
    const backupDirs = await fs.readdir(backupPath);
    
    for (const dir of backupDirs) {
      if (dir === 'report.json') continue;
      
      const sourceBackupPath = path.join(backupPath, dir);
      const originalSourceDir = config.sourceDirs.find(sd => path.basename(sd) === dir);
      
      if (!originalSourceDir) continue;
      
      const absoluteSourceDir = path.resolve(process.cwd(), originalSourceDir);
      const { files } = await getFileStats(sourceBackupPath);

      for (const file of files) {
        const relativePath = path.relative(sourceBackupPath, file);
        const targetPath = path.join(absoluteSourceDir, relativePath);
        
        const result = await copyFileWithStats(file, targetPath);
        
        if (result.success) {
          if (!restoredFiles.includes(targetPath)) {
            restoredFiles.push(targetPath);
          }
        } else {
          if (!failedFiles.includes(targetPath)) {
            failedFiles.push(targetPath);
          }
        }
      }
    }
  }

  return {
    success: failedFiles.length === 0,
    restoredFiles,
    failedFiles,
    backupChain
  };
}
