import { Peer } from './peer';

export interface Server {
  id: number;
  address: string;
  interface: string;
  listen_port: string;
  endpoint: string;
  private_key: string;
  public_key: string;
  shared_key: string;
  is_running: boolean;
  post_up: string;
  post_down: string;
  configuration: string;
  subnet: number;
  read_only: number;
  peers: Peer[];
}
