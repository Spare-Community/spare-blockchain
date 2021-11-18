import asyncio
import pytest
import time
from chia.simulator.simulator_protocol import FarmNewBlockProtocol
from chia.types.peer_info import PeerInfo
from chia.util.ints import uint16, uint32, uint64
from tests.setup_nodes import setup_simulators_and_wallets
from chia.data_layer.data_layer_wallet import DataLayerWallet
from chia.wallet.dlo_wallet.dlo_wallet import DLOWallet
from chia.wallet.db_wallet.db_wallet_puzzles import create_host_fullpuz
from chia.types.blockchain_format.program import Program
from chia.types.announcement import Announcement
from blspy import AugSchemeMPL
from chia.types.spend_bundle import SpendBundle
from chia.consensus.block_rewards import calculate_pool_reward, calculate_base_farmer_reward
from tests.time_out_assert import time_out_assert
from chia.wallet.util.merkle_tree import MerkleTree
from chia.wallet.transaction_record import TransactionRecord
from chia.wallet.util.transaction_type import TransactionType


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop


class TestDLWallet:
    @pytest.fixture(scope="function")
    async def wallet_node(self):
        async for _ in setup_simulators_and_wallets(1, 1, {}):
            yield _

    @pytest.fixture(scope="function")
    async def two_wallet_nodes(self):
        async for _ in setup_simulators_and_wallets(1, 2, {}):
            yield _

    @pytest.fixture(scope="function")
    async def three_wallet_nodes(self):
        async for _ in setup_simulators_and_wallets(1, 3, {}):
            yield _

    @pytest.fixture(scope="function")
    async def two_wallet_nodes_five_freeze(self):
        async for _ in setup_simulators_and_wallets(1, 2, {}):
            yield _

    @pytest.fixture(scope="function")
    async def three_sim_two_wallets(self):
        async for _ in setup_simulators_and_wallets(3, 2, {}):
            yield _

    @pytest.mark.asyncio
    async def test_update_coin(self, three_wallet_nodes):
        num_blocks = 5
        full_nodes, wallets = three_wallet_nodes
        full_node_api = full_nodes[0]
        full_node_server = full_node_api.server
        wallet_node_0, server_0 = wallets[0]
        wallet_node_1, server_1 = wallets[1]
        wallet_node_2, server_2 = wallets[2]
        wallet_0 = wallet_node_0.wallet_state_manager.main_wallet
        wallet_1 = wallet_node_1.wallet_state_manager.main_wallet
        wallet_2 = wallet_node_2.wallet_state_manager.main_wallet

        ph = await wallet_0.get_new_puzzlehash()
        ph1 = await wallet_1.get_new_puzzlehash()
        ph2 = await wallet_2.get_new_puzzlehash()

        await server_0.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)
        await server_1.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)
        await server_2.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)

        for i in range(1, num_blocks):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph))

        # def wallet_height_at_least(wallet_node, h):
        #     height = wallet_node.wallet_state_manager.blockchain.get_peak_height()
        #     if height == h:
        #         return True
        #     return False
        #
        # await time_out_assert(10, wallet_height_at_least, True, wallet_node_1, 4)
        # await time_out_assert(10, node_height_at_least, True, full_node_1, 4)
        # await time_out_assert(10, node_height_at_least, True, full_node_2, 4)

        funds = sum(
            [
                calculate_pool_reward(uint32(i)) + calculate_base_farmer_reward(uint32(i))
                for i in range(1, num_blocks - 1)
            ]
        )

        # print(f" - - - - - - - A {funds}")
        await time_out_assert(10, wallet_0.get_unconfirmed_balance, funds)
        await time_out_assert(10, wallet_0.get_confirmed_balance, funds)
        # print(f" - - - - - - - B {await wallet_0.get_confirmed_balance()}")

        nodes = [Program.to("thing").get_tree_hash(), Program.to([8]).get_tree_hash()]
        current_tree = MerkleTree(nodes)
        current_root = current_tree.calculate_root()

        # Wallet1 sets up DLWallet1 without any backup set
        async with wallet_node_0.wallet_state_manager.lock:
            dl_wallet_0: DataLayerWallet = await DataLayerWallet.create_new_dl_wallet(
                wallet_node_0.wallet_state_manager, wallet_0, uint64(101), current_root
            )

        # print(f" - - - - - - - C {await wallet_0.get_confirmed_balance()}")

        # await time_out_assert(15, dl_wallet_0.get_confirmed_balance, 0)
        # await time_out_assert(15, dl_wallet_0.get_unconfirmed_balance, 0)
        # await asyncio.sleep(30)

        print(f" - - - - - - - D {await dl_wallet_0.get_confirmed_balance()}")
        print(f" - - - - - - - D {await dl_wallet_0.get_unconfirmed_balance()}")

        for i in range(1, num_blocks*2):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph))

        await time_out_assert(15, dl_wallet_0.get_confirmed_balance, 101)
        await time_out_assert(15, dl_wallet_0.get_unconfirmed_balance, 101)

        print(f" - - - - - - - E {await dl_wallet_0.get_confirmed_balance()}")
        print(f" - - - - - - - E {await dl_wallet_0.get_unconfirmed_balance()}")

        assert dl_wallet_0.dl_info.root_hash == current_root

        nodes.append(Program.to("beep").get_tree_hash())
        new_merkle_tree = MerkleTree(nodes)
        await dl_wallet_0.create_update_state_spend(new_merkle_tree.calculate_root())

        print(f" - - - - - - - F {await dl_wallet_0.get_confirmed_balance()}")
        print(f" - - - - - - - F {await dl_wallet_0.get_unconfirmed_balance()}")

        for i in range(1, num_blocks * 80):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph))
            # await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph))
            print(f" - - - - - - {i} G {await dl_wallet_0.get_confirmed_balance()}")
            print(f" - - - - - - - G {await dl_wallet_0.get_unconfirmed_balance()}")
            x = await dl_wallet_0.get_unconfirmed_balance()
            if x == 101:
                print(f" + + + + + {i}")
                break

        await asyncio.sleep(30)
        print(f" - - - - - - - H {await dl_wallet_0.get_confirmed_balance()}")
        print(f" - - - - - - - H {await dl_wallet_0.get_unconfirmed_balance()}")
        await time_out_assert(15, dl_wallet_0.get_confirmed_balance, 101)
        print(f" - - - - - - - I {await dl_wallet_0.get_confirmed_balance()}")
        print(f" - - - - - - - I {await dl_wallet_0.get_unconfirmed_balance()}")
        await time_out_assert(15, dl_wallet_0.get_unconfirmed_balance, 101)

        print(f" - - - - - - - J {await dl_wallet_0.get_confirmed_balance()}")
        print(f" - - - - - - - J {await dl_wallet_0.get_unconfirmed_balance()}")

        assert dl_wallet_0.dl_info.root_hash == new_merkle_tree.calculate_root()
        coins = await dl_wallet_0.select_coins(1)
        coin = coins.pop()
        assert (
            coin.puzzle_hash
            == create_host_fullpuz(
                dl_wallet_0.dl_info.current_inner_inner,
                new_merkle_tree.calculate_root(),
                dl_wallet_0.dl_info.origin_coin.name(),
            ).get_tree_hash()
        )

    @pytest.mark.asyncio
    async def _test_announce_coin(self, three_wallet_nodes):
        num_blocks = 5
        full_nodes, wallets = three_wallet_nodes
        full_node_api = full_nodes[0]
        full_node_server = full_node_api.server
        wallet_node_0, server_0 = wallets[0]
        wallet_node_1, server_1 = wallets[1]
        wallet_node_2, server_2 = wallets[2]
        wallet_0 = wallet_node_0.wallet_state_manager.main_wallet
        wallet_1 = wallet_node_1.wallet_state_manager.main_wallet
        wallet_2 = wallet_node_2.wallet_state_manager.main_wallet

        ph = await wallet_0.get_new_puzzlehash()
        ph1 = await wallet_1.get_new_puzzlehash()
        ph2 = await wallet_2.get_new_puzzlehash()

        await server_0.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)
        await server_1.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)
        await server_2.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)

        for i in range(1, num_blocks):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph))

        funds = sum(
            [
                calculate_pool_reward(uint32(i)) + calculate_base_farmer_reward(uint32(i))
                for i in range(1, num_blocks - 1)
            ]
        )

        await time_out_assert(10, wallet_0.get_unconfirmed_balance, funds)
        await time_out_assert(10, wallet_0.get_confirmed_balance, funds)

        nodes = [Program.to("thing").get_tree_hash(), Program.to([8]).get_tree_hash()]
        current_tree = MerkleTree(nodes)
        current_root = current_tree.calculate_root()

        # Wallet1 sets up DLWallet1 without any backup set
        async with wallet_node_0.wallet_state_manager.lock:
            dl_wallet_0: DataLayerWallet = await DataLayerWallet.create_new_dl_wallet(
                wallet_node_0.wallet_state_manager, wallet_0, uint64(101), current_root
            )

        for i in range(1, num_blocks):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph1))

        await time_out_assert(15, dl_wallet_0.get_confirmed_balance, 101)
        await time_out_assert(15, dl_wallet_0.get_unconfirmed_balance, 101)
        sb = await dl_wallet_0.create_report_spend()
        ann = Announcement(sb.coin_spends[0].coin.puzzle_hash, current_root)
        announcements = set([ann.name()])
        tr = await wallet_1.generate_signed_transaction(200, ph2, puzzle_announcements_to_consume=announcements)
        sb = SpendBundle.aggregate([tr.spend_bundle, sb])
        tr = TransactionRecord(
            confirmed_at_height=uint32(0),
            created_at_time=uint64(int(time.time())),
            to_puzzle_hash=ph2,
            amount=uint64(200),
            fee_amount=uint64(0),
            confirmed=False,
            sent=uint32(0),
            spend_bundle=sb,
            additions=sb.additions(),
            removals=sb.removals(),
            wallet_id=dl_wallet_0.id(),
            sent_to=[],
            trade_id=None,
            type=uint32(TransactionType.OUTGOING_TX.value),
            name=sb.name(),
        )
        await wallet_1.push_transaction(tr)

        for i in range(1, num_blocks):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph1))

        await time_out_assert(15, wallet_2.get_confirmed_balance, 200)
        await time_out_assert(15, wallet_2.get_unconfirmed_balance, 200)

    @pytest.mark.asyncio
    async def _test_dlo_wallet(self, three_wallet_nodes):
        num_blocks = 5
        full_nodes, wallets = three_wallet_nodes
        full_node_api = full_nodes[0]
        full_node_server = full_node_api.server
        wallet_node_0, server_0 = wallets[0]
        wallet_node_1, server_1 = wallets[1]
        wallet_node_2, server_2 = wallets[2]
        wallet_0 = wallet_node_0.wallet_state_manager.main_wallet
        wallet_1 = wallet_node_1.wallet_state_manager.main_wallet
        wallet_2 = wallet_node_2.wallet_state_manager.main_wallet

        ph = await wallet_0.get_new_puzzlehash()
        ph1 = await wallet_1.get_new_puzzlehash()
        ph2 = await wallet_2.get_new_puzzlehash()

        await server_0.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)
        await server_1.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)
        await server_2.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)

        for i in range(1, num_blocks):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph))

        funds = sum(
            [
                calculate_pool_reward(uint32(i)) + calculate_base_farmer_reward(uint32(i))
                for i in range(1, num_blocks - 1)
            ]
        )

        await time_out_assert(10, wallet_0.get_unconfirmed_balance, funds)
        await time_out_assert(10, wallet_0.get_confirmed_balance, funds)

        nodes = [Program.to("thing").get_tree_hash(), Program.to([8]).get_tree_hash()]
        current_tree = MerkleTree(nodes)
        current_root = current_tree.calculate_root()

        # Wallet1 sets up DLWallet1
        async with wallet_node_0.wallet_state_manager.lock:
            dl_wallet_0: DataLayerWallet = await DataLayerWallet.create_new_dl_wallet(
                wallet_node_0.wallet_state_manager, wallet_0, uint64(101), current_root
            )

        for i in range(1, num_blocks):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph1))

        await time_out_assert(15, dl_wallet_0.get_confirmed_balance, 101)
        await time_out_assert(15, dl_wallet_0.get_unconfirmed_balance, 101)

        # Wallet1 sets up DLOWallet1
        async with wallet_node_1.wallet_state_manager.lock:
            dlo_wallet_1: DLOWallet = await DLOWallet.create_new_dlo_wallet(
                wallet_node_1.wallet_state_manager, wallet_1,
            )

        for i in range(1, num_blocks):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph1))

        await time_out_assert(15, dlo_wallet_1.get_confirmed_balance, 0)
        await time_out_assert(15, dlo_wallet_1.get_unconfirmed_balance, 0)
        # leaf_reveal: bytes,
        # host_genesis_id: bytes32,
        # claim_target: bytes32,
        # recovery_target: bytes32,
        # recovery_timelock: uint64,
        tr = await dlo_wallet_1.generate_datalayer_offer_spend(
            uint64(201),
            Program.to("thing").get_tree_hash(),
            dl_wallet_0.dl_info.origin_coin.name(),
            await wallet_2.get_new_puzzlehash(),
            await wallet_1.get_new_puzzlehash(),
            10,
        )
        await wallet_1.push_transaction(tr)

        for i in range(1, num_blocks):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph1))

        # create a second DLO Wallet and claim the coin
        async with wallet_node_2.wallet_state_manager.lock:
            dlo_wallet_2: DLOWallet = await DLOWallet.create_new_dlo_wallet(
                wallet_node_2.wallet_state_manager, wallet_2,
            )
        offer_coin = await dlo_wallet_1.get_coin()
        full_puzzle, db_innerpuz_hash, current_root = await dl_wallet_0.get_info_for_offer_claim()
        inclusion_proof = current_tree.generate_proof(Program.to("thing").get_tree_hash()),
        sb2 = await dlo_wallet_2.claim_dl_offer(offer_coin, full_puzzle, db_innerpuz_hash, current_root, inclusion_proof)
        sb = await dl_wallet_0.create_report_spend()
        sb = SpendBundle.aggregate([sb2, sb])
        tr = TransactionRecord(
            confirmed_at_height=uint32(0),
            created_at_time=uint64(int(time.time())),
            to_puzzle_hash=ph2,
            amount=uint64(201),
            fee_amount=uint64(0),
            confirmed=False,
            sent=uint32(0),
            spend_bundle=sb,
            additions=sb.additions(),
            removals=sb.removals(),
            wallet_id=dl_wallet_0.id(),
            sent_to=[],
            trade_id=None,
            type=uint32(TransactionType.OUTGOING_TX.value),
            name=sb.name(),
        )
        await wallet_2.push_transaction(tr)
        for i in range(1, num_blocks):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph1))

        await time_out_assert(15, wallet_2.get_confirmed_balance, 201)
        await time_out_assert(15, wallet_2.get_unconfirmed_balance, 201)
