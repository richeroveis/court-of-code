import {
  createClient,
  createAccount,
  generatePrivateKey,
} from "genlayer-js";
import { studionet } from "genlayer-js/chains";

// Deployed CourtOfCode tribunal on studionet (chain 61999).
export const DEFAULT_CONTRACT = "0x5049635f17E614f3BE0D3446af166DBC8E61c3eC";
export const STUDIONET_RPC = "https://studio.genlayer.com/api";

const CONTRACT_KEY = "courtofcode.contract";

export function contractAddress(): string {
  try {
    return localStorage.getItem(CONTRACT_KEY) || DEFAULT_CONTRACT;
  } catch {
    return DEFAULT_CONTRACT;
  }
}

export function setContractAddress(addr: string) {
  try {
    localStorage.setItem(CONTRACT_KEY, addr);
  } catch {
    /* ignore */
  }
}

export type WalletMode = "burner" | "metamask";

export interface WalletState {
  mode: WalletMode;
  address: string;
  client: ReturnType<typeof createClient>;
  account?: ReturnType<typeof createAccount>;
}

const PK_KEY = "courtofcode.burner.pk";

export function getOrCreateBurnerKey(): string {
  let pk = "";
  try {
    pk = localStorage.getItem(PK_KEY) || "";
  } catch {
    pk = "";
  }
  if (!pk) {
    pk = generatePrivateKey();
    try {
      localStorage.setItem(PK_KEY, pk);
    } catch {
      /* ignore */
    }
  }
  return pk;
}

export function rotateBurner(): string {
  const pk = generatePrivateKey();
  try {
    localStorage.setItem(PK_KEY, pk);
  } catch {
    /* ignore */
  }
  return pk;
}

export function connectBurner(): WalletState {
  const account = createAccount(getOrCreateBurnerKey());
  const client = createClient({ chain: studionet, account });
  return { mode: "burner", address: account.address, client, account };
}

export async function connectMetaMask(): Promise<WalletState> {
  const eth = (window as unknown as { ethereum?: EthereumProvider }).ethereum;
  if (!eth) {
    throw new Error("No EIP-1193 provider found. Install MetaMask to use it.");
  }
  const accounts = (await eth.request({
    method: "eth_requestAccounts",
  })) as string[];
  const address = accounts[0];
  const client = createClient({ provider: eth, account: address, chain: studionet });
  return { mode: "metamask", address, client };
}

type EthereumProvider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  on?: (event: string, handler: (...args: unknown[]) => void) => void;
};

export function readContract<T = unknown>(
  wallet: WalletState,
  functionName: string,
  args: unknown[] = [],
): Promise<T> {
  return wallet.client.readContract({
    address: wallet.address,
    functionName,
    args: args as never,
  }) as Promise<T>;
}

export interface WriteResult {
  txHash: string;
  statusName: string;
  succeeded: boolean;
}

// A write is submitted, then we poll the receipt until it reaches FINALIZED.
// genlayer-js receipts use snake_case (status_name, consensus_data.leader_receipt).
export async function writeContract(
  wallet: WalletState,
  functionName: string,
  args: unknown[],
  opts: { leaderOnly?: boolean } = {},
): Promise<WriteResult> {
  const hash = (await wallet.client.writeContract({
    address: wallet.address,
    functionName,
    args: args as never,
    value: 0n,
    leaderOnly: opts.leaderOnly ?? true,
  })) as string;

  const receipt = (await wallet.client.waitForTransactionReceipt({
    hash,
    interval: 3000,
    retries: 60,
  })) as ReceiptLike;

  return {
    txHash: hash,
    statusName: receiptStatus(receipt),
    succeeded: receiptSucceeded(receipt),
  };
}

type ReceiptLike = Record<string, unknown>;

function receiptStatus(receipt: ReceiptLike): string {
  return String(receipt.status_name ?? receipt.statusName ?? "UNKNOWN");
}

function receiptSucceeded(receipt: ReceiptLike): boolean {
  const cd = (receipt.consensus_data ?? receipt.consensusData) as
    | ReceiptLike
    | undefined;
  const leaders = cd?.leader_receipt ?? cd?.leaderReceipt;
  if (!Array.isArray(leaders) || leaders.length === 0) return false;
  const leader = leaders[0] as ReceiptLike;
  return leader.execution_result === "SUCCESS" || leader.executionResult === "SUCCESS";
}
