export interface BackupConfig {
  sourceDirs: string[];
  targetDir: string;
  strategy: 'full' | 'incremental';
  retentionCount: number;
  cronExpression: string;
  excludePatterns: string[];
}

export interface BackupReport {
  backupName: string;
  type: 'full' | 'incremental';
  startTime: Date;
  endTime: Date;
  duration: number;
  fileCount: number;
  totalSize: number;
  successFiles: string[];
  failedFiles: { file: string; error: string }[];
}

export interface BackupInfo {
  name: string;
  timestamp: Date;
  type: 'full' | 'incremental';
  size: number;
  fileCount: number;
}
