# -*- coding: utf-8 -*-
"""
Created on Fri Mar 22 13:16:24 2019

@author: mpokam
"""

from hashlib import sha256
import json
import time

from uuid import uuid4
from urllib.parse import urlparse

from flask import Flask, jsonify, request
import requests

class Block:
    def __init__(self, index, nonce, previous_hash, timestamp, transactions):
        self.index = index
        self.transactions = transactions
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.nonce = nonce

    def compute_hash(self):
        """
        A function that creates the hash of the block contents.
        """
        block_string = json.dumps(self.__dict__, sort_keys=True)
        return sha256(block_string.encode()).hexdigest()
    
    
class Blockchain:
    
    # difficulty of our PoW algorithm
    difficulty = 2
    
    def __init__(self):
        self.unconfirmed_transactions = [] # data yet to get into blockchain
        self.chain = []
        self.create_genesis_block()
        self.peers = set()
        
    def create_genesis_block(self):
        """
        A function to generate genesis block and append it to
        the chain. The block has index 0, previous_hash as 0, and
        a valid hash.
        """
        genesis_block = Block(0, 0, "0", time.time(), [])
        genesis_block.hash = genesis_block.compute_hash()
        self.chain.append(genesis_block)
    
    @property
    def last_block(self):
        return self.chain[-1]
        
    def is_valid_proof(self, block, block_hash):
        """
        Check if block_hash is valid hash of block and satisfies
        the difficulty criteria.
        """
        
        return (block_hash.startswith('0' * Blockchain.difficulty) and
                block_hash == block.hash)
        
    def proof_of_work(self, block):
        """
        Function that tries different values of nonce to get a hash
        that satisfies our difficulty criteria.
        """
        
        block.nonce = 0
        
        computed_hash = block.compute_hash()
        while not computed_hash.startswith('0' * Blockchain.difficulty):
            block.nonce += 1
            computed_hash = block.compute_hash()
        
        return computed_hash
    
    
    def add_new_transaction(self, transaction):
            self.unconfirmed_transactions.append(transaction)
    
    def mine(self):
        """
        This function serves as an interface to add the pending
        transactions to the blockchain by adding them to the block
        and figuring out Proof of Work.
        """
        if not self.unconfirmed_transactions:
            return False
        last_block = self.last_block
        
        new_block = Block(index=last_block.index + 1,
                          nonce=0,
                          previous_hash=last_block.compute_hash(),
                          timestamp=time.time(),
                          transactions=self.unconfirmed_transactions)
        
        proof = self.proof_of_work(new_block)
        
        block_data = {'index': new_block.index,
                  'nonce': new_block.nonce,
                  'previous_hash': new_block.previous_hash,
                  'timestamp': new_block.timestamp,
                  'transactions': new_block.transactions,
                  'hash': proof
                  }
        
        self.announce_new_block(block_data)
        self.unconfirmed_transactions = []
        return new_block.index
    
    def add_node(self, address):
        parsed_url = urlparse(address)
        self.peers.add(parsed_url.netloc)
        
    def consensus(self):
        network = self.peers
        longest_chain = None
        max_length = len(self.chain)
        for node in network:
            response = requests.get(f'http://{node}/chain')
            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']
                if length > max_length:
                    max_length = length
                    longest_chain = chain
        if longest_chain:
            self.chain=[]
            for data in longest_chain:
                block = Block(index=data['index'], 
                nonce=data['nonce'], 
                previous_hash=data['previous_hash'], 
                timestamp=data['timestamp'], 
                transactions=data['transactions'])
                
                block.hash = data['hash']
                
                self.chain.append(block)
            return True
        return False
    
    def announce_new_block(self, block_data):
        network = self.peers
        for peer in network:
            url = f'http://{peer}/add_block'
            #data=json.dumps(block_data.__dict__, sort_keys=True)
            data=json.dumps(block_data, sort_keys=True)
            #print("post data: ", data, "\n")
            requests.post(url, data)
    

app =  Flask(__name__)
# the node's copy of blockchain
blockchain = Blockchain()


@app.route('/new_transaction', methods=['POST'])
def new_transaction():
    tx_data = request.get_json()
    required_fields = ["author", "content"]
    for field in required_fields:
        if not tx_data.get(field):
            return "Invlaid transaction data", 404
    tx_data["timestamp"] = time.time()
    blockchain.add_new_transaction(tx_data)
    return "Success", 201


@app.route('/chain', methods=['GET'])
def get_chain():
    chain_data = []
    print ("chain: ", blockchain.chain, "\n")
    for block in blockchain.chain:
        chain_data.append(block.__dict__)
    return json.dumps({"length": len(chain_data),
                       "chain": chain_data})

@app.route('/mine', methods=['GET'])
def mine_unconfirmed_transactions():
    global blockchain
    result = blockchain.mine()
    if not result:
        return "No transactions to mine"
    
    
    return "Block #{} is mined.".format(result)
# endpoint to query unconfirmed transactions

@app.route('/pending_tx')
def get_pending_tx():
    return json.dumps(blockchain.unconfirmed_transactions)

# the address to other participating members of the network
# endpoint to add new peers to the network.
@app.route('/add_peers', methods=['POST'])
def connect_node():
    json = request.get_json()
    nodes = json.get('nodes')
    if nodes is None:
        return "No node", 400
    for node in nodes:
        blockchain.add_node(node)
    response = {'message': 'All the nodes are now connected. The blockchain  now contains the following nodes:',
                'total_nodes': list(blockchain.peers)}
    return jsonify(response), 201

# endpoint to executing longest chain wins consensus.
@app.route('/consensus', methods=['GET'])
def consensus():
    is_chain_replaced = blockchain.consensus()
    if is_chain_replaced:
        response = {'message': 'The peers had different chains so the chain was replaced by the longest one.'}
    else:
        response = {'message': 'All good. The chain is the longest one.'}
    return jsonify(response), 200
    

# endpoint to add a block mined by someone else to the node's chain.
@app.route('/add_block', methods=['POST'])
def validate_and_add_block():
    data = request.get_json(force=True)  

    proof = data['hash']    
    block = Block(index=data['index'], 
                  nonce=data['nonce'], 
                  previous_hash=data['previous_hash'], 
                  timestamp=data['timestamp'], 
                  transactions=data['transactions'])
    block.hash = proof
    
    global blockchain
    previous_hash = blockchain.last_block.compute_hash()
    
    if previous_hash != block.previous_hash:
        return "The block was discarded by the node", 400
        
    if not blockchain.is_valid_proof(block, proof):
        return "The block was discarded by the node", 400
        
    blockchain.chain.append(block)
    return "Block added to the chain", 201

    
def announce_new_block(block):
    for peer in blockchain.peers:
        url = "http://{}/add_block".format(peer)
        requests.post(url, data=json.dumps(block.__dict__, sort_keys=True))
        
app.run(host="0.0.0.0", port=8000)




