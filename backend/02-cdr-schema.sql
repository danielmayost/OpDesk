-- OpDesk CDR table for pure-Asterisk mode
--
-- This file is the second init script mounted into the OpDesk MariaDB container
-- (see compose.yml). It creates the `cdr` table that backend/db_manager.py
-- queries for the call log + analytics, and seeds a few example rows so the
-- panel has something to show on first boot.
--
-- Schema mirrors the standard FreePBX asteriskcdrdb.cdr layout so the existing
-- get_call_log_from_db / get_cdr_by_linkedid / get_call_log_count_from_db
-- queries work unchanged. Two-leg rows per call (sequence = 1 first leg,
-- sequence = 2 last leg) reproduce what res_pjsip's cdr_mysql backend writes.
--
-- MariaDB 5.5 compatibility: TIMESTAMP for auto-populated columns, VARCHAR(191)
-- for any indexed VARCHAR under utf8mb4 (767-byte InnoDB key limit).

USE OpDesk;

CREATE TABLE IF NOT EXISTS cdr (
    calldate       DATETIME        NOT NULL,
    clid           VARCHAR(80)     NOT NULL DEFAULT '',
    src            VARCHAR(80)     NOT NULL DEFAULT '',
    dst            VARCHAR(80)     NOT NULL DEFAULT '',
    dcontext       VARCHAR(80)     NOT NULL DEFAULT '',
    channel        VARCHAR(80)     NOT NULL DEFAULT '',
    dstchannel     VARCHAR(80)     NOT NULL DEFAULT '',
    lastapp        VARCHAR(80)     NOT NULL DEFAULT '',
    lastdata       VARCHAR(80)     NOT NULL DEFAULT '',
    duration       INT             NOT NULL DEFAULT 0,
    billsec        INT             NOT NULL DEFAULT 0,
    disposition    VARCHAR(45)     NOT NULL DEFAULT '',
    amaflags       INT             NOT NULL DEFAULT 0,
    accountcode    VARCHAR(20)     NOT NULL DEFAULT '',
    uniqueid       VARCHAR(32)     NOT NULL DEFAULT '',
    linkedid       VARCHAR(32)     NOT NULL DEFAULT '',
    sequence       INT             NOT NULL DEFAULT 0,
    cnam           VARCHAR(80)     NULL,
    recordingfile  VARCHAR(255)    NULL,
    userfield      VARCHAR(255)    NULL,

    INDEX idx_calldate (calldate),
    INDEX idx_linkedid (linkedid),
    INDEX idx_linkedid_seq (linkedid, sequence),
    INDEX idx_src (src),
    INDEX idx_dst (dst),
    INDEX idx_dcontext (dcontext),
    INDEX idx_disposition (disposition)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================================================
-- Seed data (only inserted on first init of an empty data volume).
-- =============================================================================

-- 1) Inbound to queue 2000, answered by agent 1001 (two legs)
INSERT INTO cdr
    (calldate, clid, src, dst, dcontext, channel, dstchannel,
     lastapp, lastdata, duration, billsec, disposition,
     uniqueid, linkedid, sequence, cnam, recordingfile, userfield)
VALUES
    ('2026-06-18 09:14:02', '"Acme Corp" <+15551234001>', '+15551234001', '2000',
     'ext-queues,2000,1', 'PJSIP/trunk-000000a1', 'PJSIP/1001-000000b1',
     'Queue', '2000,t,,', 47, 39, 'ANSWERED',
     '1771297842.11', '1771297842.11', 1, 'Acme Corp', 'q-2000-1001-1771297842-11.wav', 'rtcp=92;rxjitter=4;'),
    ('2026-06-18 09:14:10', '"Acme Corp" <+15551234001>', '2000', '1001',
     'from-queue', 'Local/1001@from-queue-000000a2;2', 'PJSIP/1001-000000b1',
     'Dial', 'PJSIP/1001,300,Ttb', 39, 39, 'ANSWERED',
     '1771297850.12', '1771297842.11', 2, 'Acme Corp', 'q-2000-1001-1771297842-11.wav', 'rtcp=92;rxjitter=4;'),

-- 2) Inbound to queue 2000, abandoned (caller hung up while waiting)
    ('2026-06-18 10:02:18', '"Maria Lopez" <+15551234002>', '+15551234002', '2000',
     'ext-queues,2000,1', 'PJSIP/trunk-000000a3', '',
     'Queue', '2000,t,,', 34, 0, 'NO ANSWER',
     '1771302138.21', '1771302138.21', 1, 'Maria Lopez', NULL, NULL),

-- 3) Direct inbound to 1002, missed (ring timeout)
    ('2026-06-18 10:48:55', '"Unknown" <+15551234003>', '+15551234003', '1002',
     'ext-local,1002,1', 'PJSIP/trunk-000000a4', '',
     'Dial', 'PJSIP/1002,40,tT', 40, 0, 'NO ANSWER',
     '1771304935.31', '1771304935.31', 1, NULL, NULL, NULL),

-- 4) Direct inbound to 1003, answered
    ('2026-06-18 11:31:09', '"John Smith" <+15551234004>', '+15551234004', '1003',
     'ext-local,1003,1', 'PJSIP/trunk-000000a5', 'PJSIP/1003-000000c1',
     'Dial', 'PJSIP/1003,60,Ttb', 162, 148, 'ANSWERED',
     '1771307469.41', '1771307469.41', 1, 'John Smith', 'in-1003-1771307469-41.wav', 'rtcp=88;rxjitter=7;'),

-- 5) Outbound from agent 1001 to a mobile number
    ('2026-06-18 12:05:33', '"1001" <1001>', '1001', '+15559876543',
     'from-internal', 'PJSIP/1001-000000d1', 'PJSIP/trunk-000000d2',
     'Dial', 'PJSIP/+15559876543@trunk,60,Ttb', 95, 88, 'ANSWERED',
     '1771309533.51', '1771309533.51', 1, NULL, 'out-1001-1771309533-51.wav', 'rtcp=80;rxjitter=12;'),

-- 6) Internal call between two extensions
    ('2026-06-17 16:42:11', '"1001" <1001>', '1001', '1002',
     'ext-local,1002,1', 'PJSIP/1001-000000e1', 'PJSIP/1002-000000e2',
     'Dial', 'PJSIP/1002,30,Ttb', 73, 64, 'ANSWERED',
     '1771232531.61', '1771232531.61', 1, NULL, 'int-1001-1002-1771232531-61.wav', NULL),

-- 7) Inbound to queue 2000 with a transfer: queue -> 1001 -> 1002 (three legs)
    ('2026-06-17 14:08:44', '"Beta Ltd" <+15551234005>', '+15551234005', '2000',
     'ext-queues,2000,1', 'PJSIP/trunk-000000f1', 'PJSIP/1001-000000f2',
     'Queue', '2000,t,,', 182, 167, 'ANSWERED',
     '1771223324.71', '1771223324.71', 1, 'Beta Ltd', 'q-2000-1001-1771223324-71.wav', 'rtcp=94;rxjitter=3;'),
    ('2026-06-17 14:08:55', '"Beta Ltd" <+15551234005>', '2000', '1001',
     'from-queue', 'Local/1001@from-queue-000000f3;2', 'PJSIP/1001-000000f2',
     'Dial', 'PJSIP/1001,300,Ttb', 39, 39, 'ANSWERED',
     '1771223335.72', '1771223324.71', 2, 'Beta Ltd', 'q-2000-1001-1771223324-71.wav', 'rtcp=94;rxjitter=3;'),
    ('2026-06-17 14:11:14', '"Beta Ltd" <+15551234005>', '2000', '1002',
     'from-internal-xfer', 'PJSIP/1001-000000f2', 'PJSIP/1002-000000f4',
     'Dial', 'PJSIP/1002,300,Ttb', 128, 128, 'ANSWERED',
     '1771223474.73', '1771223324.71', 3, 'Beta Ltd', 'q-2000-1001-1771223324-71.wav', 'rtcp=94;rxjitter=3;'),

-- 8) Busy (extension rejected)
    ('2026-06-16 11:20:05', '"+15551234006" <+15551234006>', '+15551234006', '1001',
     'ext-local,1001,1', 'PJSIP/trunk-000000b5', '',
     'Dial', 'PJSIP/1001,30,tT', 0, 0, 'BUSY',
     '1771114805.81', '1771114805.81', 1, NULL, NULL, NULL);
