BEGIN;

-- Assets
INSERT INTO assets (code, name) VALUES
    ('GOLD', 'Gold Coins'),
    ('DIAMOND', 'Diamonds'),
    ('LOYALTY', 'Loyalty Points')
ON CONFLICT (code) DO NOTHING;

-- System wallets
INSERT INTO wallets (owner_type, owner_ref, name) VALUES
    ('SYSTEM', 'system:treasury', 'Treasury'),
    ('SYSTEM', 'system:revenue', 'Revenue')
ON CONFLICT (owner_type, owner_ref) DO NOTHING;

-- Users
INSERT INTO users (username) VALUES
    ('alice'),
    ('bob')
ON CONFLICT (username) DO NOTHING;

-- User wallets
INSERT INTO wallets (owner_type, owner_ref, name)
SELECT 'USER', CONCAT('user:', id), CONCAT(username, ' Wallet')
FROM users
ON CONFLICT (owner_type, owner_ref) DO NOTHING;

-- Initial balances for all wallets/assets
INSERT INTO wallet_balances (wallet_id, asset_id, balance)
SELECT w.id, a.id,
    CASE
        WHEN w.owner_ref = 'system:treasury' AND a.code = 'GOLD' THEN 1000000
        WHEN w.owner_ref = 'system:treasury' AND a.code = 'DIAMOND' THEN 500000
        WHEN w.owner_ref = 'system:treasury' AND a.code = 'LOYALTY' THEN 2000000
        WHEN w.owner_ref = 'system:revenue' THEN 0
        WHEN w.owner_ref = 'user:1' AND a.code = 'GOLD' THEN 1000
        WHEN w.owner_ref = 'user:1' AND a.code = 'DIAMOND' THEN 50
        WHEN w.owner_ref = 'user:1' AND a.code = 'LOYALTY' THEN 200
        WHEN w.owner_ref = 'user:2' AND a.code = 'GOLD' THEN 500
        WHEN w.owner_ref = 'user:2' AND a.code = 'DIAMOND' THEN 20
        WHEN w.owner_ref = 'user:2' AND a.code = 'LOYALTY' THEN 100
        ELSE 0
    END
FROM wallets w
CROSS JOIN assets a
ON CONFLICT (wallet_id, asset_id) DO NOTHING;

COMMIT;

