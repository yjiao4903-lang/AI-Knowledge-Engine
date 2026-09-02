export type WorkerLauncherId = 'codex' | 'claude' | 'terminal';

export interface WorkerLauncherInfo {
  id: WorkerLauncherId;
  label: string;
  available: boolean;
}

export interface WorkerLaunchersResponse {
  launchers: WorkerLauncherInfo[];
}

export interface LaunchWorkerResponse {
  task_id: string;
  launcher: WorkerLauncherId;
  launched: true;
  pid: number;
  status: 'PROCESSING';
  task_path: string;
}
