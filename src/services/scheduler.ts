import * as cron from 'node-cron';
import chalk from 'chalk';
import { BackupConfig } from '../types';
import { performBackup, cleanupOldBackups } from './backup';
import { formatDuration, formatBytes } from '../utils/file';

export function startScheduler(config: BackupConfig): void {
  console.log(chalk.blue(`\n定时备份已启动，Cron 表达式: ${config.cronExpression}`));
  console.log(chalk.gray(`按 Ctrl+C 停止程序\n`));

  cron.schedule(config.cronExpression, async () => {
    try {
      console.log(chalk.yellow(`\n[${new Date().toLocaleString()}] 开始定时备份...`));
      
      await cleanupOldBackups(config);
      
      const report = await performBackup(config);
      
      console.log(chalk.green(`\n✅ 备份完成!`));
      console.log(chalk.white(`备份名称: ${report.backupName}`));
      console.log(chalk.white(`备份类型: ${report.type === 'full' ? '全量' : '增量'}`));
      console.log(chalk.white(`文件数量: ${report.fileCount}`));
      console.log(chalk.white(`总大小: ${formatBytes(report.totalSize)}`));
      console.log(chalk.white(`耗时: ${formatDuration(report.duration)}`));
      
      if (report.failedFiles.length > 0) {
        console.log(chalk.red(`失败文件: ${report.failedFiles.length}`));
      }
    } catch (error) {
      console.error(chalk.red(`备份失败: ${(error as Error).message}`));
    }
  });
}
