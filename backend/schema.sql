CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(160) UNIQUE NOT NULL,
  password VARCHAR(100) NOT NULL,
  name VARCHAR(80) NOT NULL,
  role ENUM('inventory_clerk','regional_manager','shift_coordinator') NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS inventory_snapshots (
  id INT AUTO_INCREMENT PRIMARY KEY,
  store_code VARCHAR(40) NOT NULL,
  store_name VARCHAR(100) NOT NULL,
  sku VARCHAR(40) NOT NULL,
  product_name VARCHAR(140) NOT NULL,
  category VARCHAR(80) NOT NULL,
  on_hand DECIMAL(12,2) NOT NULL,
  daily_sales JSON NOT NULL,
  lead_time_days INT NOT NULL,
  safety_days DECIMAL(5,2) NOT NULL,
  pack_size INT NOT NULL,
  expiry_date DATE NULL,
  substitute_sku VARCHAR(40) NULL,
  substitute_name VARCHAR(140) NULL,
  snapshot_date DATE NOT NULL,
  status ENUM('counted','forecasted','reviewed') NOT NULL DEFAULT 'counted',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_snapshot (store_code, sku, snapshot_date)
);
CREATE TABLE IF NOT EXISTS replenishment_recommendations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  snapshot_id INT NOT NULL,
  avg_daily DECIMAL(12,2) NOT NULL,
  safety_stock DECIMAL(12,2) NOT NULL,
  reorder_point DECIMAL(12,2) NOT NULL,
  recommended_qty INT NOT NULL,
  reason VARCHAR(255) NOT NULL,
  status ENUM('draft','blocked','submitted','approved','overridden') NOT NULL DEFAULT 'draft',
  override_qty INT NULL,
  calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (snapshot_id) REFERENCES inventory_snapshots(id)
);
CREATE TABLE IF NOT EXISTS approval_orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  recommendation_id INT NOT NULL,
  store_code VARCHAR(40) NOT NULL,
  delivery_shift ENUM('morning','afternoon','night') NOT NULL,
  approved_qty INT NOT NULL,
  reviewer_id INT NULL,
  status ENUM('pending','approved','rejected','distributed') NOT NULL DEFAULT 'pending',
  review_note VARCHAR(255) NULL,
  reviewed_at TIMESTAMP NULL,
  FOREIGN KEY (recommendation_id) REFERENCES replenishment_recommendations(id)
);
CREATE TABLE IF NOT EXISTS dispatch_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  approval_id INT NOT NULL,
  recipient_name VARCHAR(100) NOT NULL,
  shift ENUM('morning','afternoon','night') NOT NULL,
  dispatched_at TIMESTAMP NULL,
  received_at TIMESTAMP NULL,
  status ENUM('queued','sent','received') NOT NULL DEFAULT 'queued',
  note VARCHAR(255) NULL,
  FOREIGN KEY (approval_id) REFERENCES approval_orders(id)
);
CREATE TABLE IF NOT EXISTS audit_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  actor_id INT NULL,
  action VARCHAR(80) NOT NULL,
  entity_type VARCHAR(80) NOT NULL,
  entity_id INT NULL,
  detail JSON NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
