//! Local-only (localhost:8899 solana-test-validator, NOT devnet, NOT
//! mainnet) round-trip dry run for solana_authority_oracle: initialize the
//! registry, push one real live-derived score (Jupiter Aggregator v6, the
//! exact numbers chains/solana/deploy/update_scores_solana.py's dry-run
//! encoded against live mainnet this same session), read the PDA back, and
//! assert every field matches what was sent.
use sha2::{Digest, Sha256};
use solana_client::rpc_client::RpcClient;
use solana_sdk::{
    commitment_config::CommitmentConfig,
    instruction::{AccountMeta, Instruction},
    pubkey::Pubkey,
    signature::{Keypair, Signer},
    system_program,
    transaction::Transaction,
};
use std::str::FromStr;
use std::time::Duration;

const PROGRAM_ID: &str = "ENVgJeWHRBH9U9w44Mx8a1L4u58AMtZYgmPXZ7ySKj8a";

fn discriminator(name: &str) -> [u8; 8] {
    let mut hasher = Sha256::new();
    hasher.update(format!("global:{name}").as_bytes());
    let result = hasher.finalize();
    let mut out = [0u8; 8];
    out.copy_from_slice(&result[..8]);
    out
}

fn methodology_hash() -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(b"authority-risk-oracle-solana-v1");
    let r = hasher.finalize();
    let mut out = [0u8; 32];
    out.copy_from_slice(&r);
    out
}

fn main() {
    let client = RpcClient::new_with_commitment(
        "http://127.0.0.1:8899".to_string(),
        CommitmentConfig::confirmed(),
    );
    let program_id = Pubkey::from_str(PROGRAM_ID).unwrap();

    let payer = Keypair::new();
    println!("payer = {}", payer.pubkey());

    let sig = client.request_airdrop(&payer.pubkey(), 2_000_000_000).unwrap();
    loop {
        if client.confirm_transaction(&sig).unwrap() {
            break;
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    println!(
        "airdrop confirmed on LOCAL test validator (localhost:8899, not devnet/mainnet), balance = {}",
        client.get_balance(&payer.pubkey()).unwrap()
    );

    let (registry_pda, _registry_bump) = Pubkey::find_program_address(&[b"registry"], &program_id);
    println!("registry PDA = {registry_pda}");

    let mut init_data = discriminator("initialize").to_vec();
    init_data.extend_from_slice(payer.pubkey().as_ref()); // admin
    init_data.extend_from_slice(payer.pubkey().as_ref()); // updater
    let init_ix = Instruction {
        program_id,
        accounts: vec![
            AccountMeta::new(registry_pda, false),
            AccountMeta::new(payer.pubkey(), true),
            AccountMeta::new_readonly(system_program::id(), false),
        ],
        data: init_data,
    };
    let bh = client.get_latest_blockhash().unwrap();
    let tx = Transaction::new_signed_with_payer(&[init_ix], Some(&payer.pubkey()), &[&payer], bh);
    let sig = client.send_and_confirm_transaction(&tx).unwrap();
    println!("initialize tx = {sig}");

    // Same target + same live-derived numbers
    // chains/solana/deploy/update_scores_solana.py's --dry-run encoded this
    // same session for Jupiter Aggregator v6 (see the journal entry citing
    // that exact command's output).
    let target = Pubkey::from_str("JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4").unwrap();
    let (score_pda, _score_bump) =
        Pubkey::find_program_address(&[b"score", target.as_ref()], &program_id);
    println!("score PDA = {score_pda}");

    let admin_key_score: u8 = 55;
    let multisig_score: u8 = 83;
    let timelock_score: u8 = 0;
    let oracle_authority_score: u8 = 100;
    let cross_exposure_score: u8 = 40;
    let composite_score: u8 = 47;
    let meth_hash = methodology_hash();

    let mut upd_data = discriminator("update_score").to_vec();
    upd_data.extend_from_slice(target.as_ref());
    upd_data.push(admin_key_score);
    upd_data.push(multisig_score);
    upd_data.push(timelock_score);
    upd_data.push(oracle_authority_score);
    upd_data.push(cross_exposure_score);
    upd_data.push(composite_score);
    upd_data.extend_from_slice(&meth_hash);

    let upd_ix = Instruction {
        program_id,
        accounts: vec![
            AccountMeta::new(registry_pda, false),
            AccountMeta::new(score_pda, false),
            AccountMeta::new(payer.pubkey(), true),
            AccountMeta::new_readonly(system_program::id(), false),
        ],
        data: upd_data,
    };
    let bh2 = client.get_latest_blockhash().unwrap();
    let tx2 = Transaction::new_signed_with_payer(&[upd_ix], Some(&payer.pubkey()), &[&payer], bh2);
    let sig2 = client.send_and_confirm_transaction(&tx2).unwrap();
    println!("update_score tx = {sig2}");

    let account = client.get_account(&score_pda).unwrap();
    println!("score account data len = {}", account.data.len());
    let data = &account.data;
    let read_target = Pubkey::new_from_array(data[8..40].try_into().unwrap());
    let read_admin = data[40];
    let read_multisig = data[41];
    let read_timelock = data[42];
    let read_oracle = data[43];
    let read_cross = data[44];
    let read_composite = data[45];
    println!(
        "read back: target={read_target} admin={read_admin} multisig={read_multisig} timelock={read_timelock} oracle={read_oracle} cross={read_cross} composite={read_composite}"
    );
    assert_eq!(read_target, target);
    assert_eq!(read_admin, admin_key_score);
    assert_eq!(read_multisig, multisig_score);
    assert_eq!(read_timelock, timelock_score);
    assert_eq!(read_oracle, oracle_authority_score);
    assert_eq!(read_cross, cross_exposure_score);
    assert_eq!(read_composite, composite_score);
    println!(
        "ALL ASSERTIONS PASSED -- local solana-test-validator (localhost only, zero value) round trip verified"
    );
}
