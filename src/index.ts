#!/usr/bin/env node

import { Command } from 'commander';
import chalk from 'chalk';
import ora from 'ora';
import * as path from 'path';
import * as readline from 'readline';
import { loadConfig } from './utils/config';
import { getBackupList, formatBytes, formatDuration } from './utils/file';
import { performBackup, cleanupOldBackups, restoreBackup } from './services/backup';
import { startScheduler } from './services/scheduler';

const program = new Command();

program
  .name('backup')
  .description('自动化本地数据备份工具')
  .version('1.0.0')
  .option('--config <path>', '配置文件路径', './config.json')
  .option('--list', '查看历史备份列表')
  .option('--restore <backupName>', '恢复到指定备份版本')
  .option('--yes', '跳过确认提示，强制执行操作')
  .option('--daemon', '以守护进程模式运行，启用定时备份');

async function confirmAction(message: string): Promise<boolean> {
  if (program.opts().yes) {
    return true;
  }

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  return new Promise((resolve) => {
    rl.question(`${message} (yes/no): `, (answer) => {
      rl.close();
      resolve(answer.toLowerCase() === 'yes' || answer.toLowerCase() === 'y');
    });
  });
}

type Spinner = ReturnType<typeof ora>;

async function performCleanup(config: any, spinner: Spinner) {
  const deleted = await cleanupOldBackups(config);
  if (deleted.length > 0) {
    spinner.succeed(`已清理 ${deleted.length} 个旧备份`);
  } else {
    spinner.succeed('无需清理旧备份');
  }
}

async function handleBackup(options: any) {
  const spinner = ora('加载配置文件...').start();
  const config = await loadConfig(options.config);
  spinner.succeed('配置文件加载成功');

  const targetDir = path.resolve(process.cwd(), config.targetDir);
  console.log(chalk.gray(`目标目录: ${targetDir}`));
  console.log(chalk.gray(`备份策略: ${config.strategy === 'full' ? '全量' : '增量'}`));
  console.log(chalk.gray(`保留份数: ${config.retentionCount}\n`));

  const cleanupSpinner = ora('检查并清理旧备份...').start();
  await performCleanup(config, cleanupSpinner);

  if (options.daemon) {
    startScheduler(config);
    return;
  }

  const backupSpinner = ora('正在执行备份...').start();
  const report = await performBackup(config);
  backupSpinner.succeed('备份完成!');

  console.log('\n' + chalk.cyan('═══════════════════════════════════════════'));
  console.log(chalk.cyan('              备份报告'));
  console.log(chalk.cyan('═══════════════════════════════════════════\n'));
  console.log(chalk.white(`备份名称: ${chalk.bold(report.backupName)}`));
  console.log(chalk.white(`备份类型: ${chalk.bold(report.type === 'full' ? '全量备份' : '增量备份')}`));
  console.log(chalk.white(`开始时间: ${chalk.bold(report.startTime.toLocaleString())}`));
  console.log(chalk.white(`结束时间: ${chalk.bold(report.endTime.toLocaleString())}`));
  console.log(chalk.white(`耗时: ${chalk.bold(formatDuration(report.duration))}`));
  console.log(chalk.white(`文件数量: ${chalk.bold(report.fileCount)}`));
  console.log(chalk.white(`总大小: ${chalk.bold(formatBytes(report.totalSize))}\n`));

  if (report.successFiles.length > 0) {
    console.log(chalk.green(`✅ 成功文件 (${report.successFiles.length} 个):`));
    report.successFiles.slice(0, 10).forEach(file => {
      console.log(chalk.gray(`  - ${file}`));
    });
    if (report.successFiles.length > 10) {
      console.log(chalk.gray(`  ... 还有 ${report.successFiles.length - 10} 个文件`));
    }
    console.log();
  }

  if (report.failedFiles.length > 0) {
    console.log(chalk.red(`❌ 失败文件 (${report.failedFiles.length} 个):`));
    report.failedFiles.forEach(({ file, error }) => {
      console.log(chalk.red(`  - ${file}: ${error}`));
    });
    console.log();
  }

  console.log(chalk.cyan('═══════════════════════════════════════════\n'));
}

async function handleList(options: any) {
  const spinner = ora('加载配置文件...').start();
  const config = await loadConfig(options.config);
  spinner.stop();

  const targetDir = path.resolve(process.cwd(), config.targetDir);
  const backups = await getBackupList(targetDir);

  if (backups.length === 0) {
    console.log(chalk.yellow('\n暂无备份记录\n'));
    return;
  }

  console.log('\n' + chalk.cyan('══════════════════════════════════════════════════════════════'));
  console.log(chalk.cyan('                     历史备份列表'));
  console.log(chalk.cyan('══════════════════════════════════════════════════════════════\n'));

  backups.forEach((backup, index) => {
    const isLatest = index === 0;
    const prefix = isLatest ? chalk.green('★ ') : '  ';
    
    console.log(`${prefix}${chalk.bold(backup.name)}`);
    console.log(`   时间: ${backup.timestamp.toLocaleString()}`);
    console.log(`   类型: ${backup.type === 'full' ? '全量' : '增量'}`);
    console.log(`   大小: ${formatBytes(backup.size)}`);
    console.log(`   文件: ${backup.fileCount} 个`);
    console.log();
  });

  console.log(chalk.cyan('══════════════════════════════════════════════════════════════\n'));
  console.log(chalk.gray(`共 ${backups.length} 个备份，保留 ${config.retentionCount} 个\n`));
}

async function handleRestore(backupName: string, options: any) {
  const spinner = ora('加载配置文件...').start();
  const config = await loadConfig(options.config);
  spinner.stop();

  console.log(chalk.yellow('\n⚠️  警告: 恢复操作将覆盖现有文件!\n'));
  console.log(chalk.white(`准备恢复备份: ${chalk.bold(backupName)}\n`));

  const confirmed = await confirmAction('确定要执行恢复操作吗？');
  if (!confirmed) {
    console.log(chalk.yellow('\n操作已取消\n'));
    process.exit(0);
  }

  const restoreSpinner = ora('正在恢复备份...').start();
  const result = await restoreBackup(backupName, config);
  restoreSpinner.succeed('恢复完成!');

  console.log('\n' + chalk.cyan('═══════════════════════════════════════════'));
  console.log(chalk.cyan('              恢复报告'));
  console.log(chalk.cyan('═══════════════════════════════════════════\n'));
  
  console.log(chalk.white(`备份链 (共 ${result.backupChain.length} 个):`));
  result.backupChain.forEach((backup, index) => {
    const type = backup.type === 'full' ? '全量' : '增量';
    console.log(chalk.gray(`  ${index + 1}. ${backup.name} (${type})`));
  });
  console.log();
  
  console.log(chalk.white(`成功恢复: ${chalk.bold(result.restoredFiles.length)} 个文件`));
  
  if (result.failedFiles.length > 0) {
    console.log(chalk.red(`失败: ${chalk.bold(result.failedFiles.length)} 个文件`));
    result.failedFiles.forEach(file => {
      console.log(chalk.red(`  - ${file}`));
    });
  }
  
  console.log(chalk.cyan('\n═══════════════════════════════════════════\n'));
}

async function main() {
  try {
    program.parse(process.argv);
    const options = program.opts();

    if (options.list) {
      await handleList(options);
    } else if (options.restore) {
      await handleRestore(options.restore, options);
    } else {
      await handleBackup(options);
    }
  } catch (error) {
    console.error(chalk.red(`\n❌ 错误: ${(error as Error).message}`));
    process.exit(1);
  }
}

main();
