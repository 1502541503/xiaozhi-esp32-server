/*
 Navicat Premium Dump SQL

 Source Server         : ai-dev
 Source Server Type    : MySQL
 Source Server Version : 80028 (8.0.28)
 Source Host           : rm-j6ca3vf35i70jyufpzo.mysql.rds.aliyuncs.com:3306
 Source Schema         : xiaozhi_backup3

 Target Server Type    : MySQL
 Target Server Version : 80028 (8.0.28)
 File Encoding         : 65001

 Date: 25/08/2025 10:38:26
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for ble_white_list
-- ----------------------------
DROP TABLE IF EXISTS `ble_white_list`;
CREATE TABLE `ble_white_list`  (
                                   `id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'ID',
                                   `pid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'appid',
                                   `ble_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '蓝牙名',
                                   `flag` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '固件标记',
                                   `remark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注',
                                   `updater` bigint NULL DEFAULT NULL COMMENT '更新者',
                                   `update_date` datetime NULL DEFAULT NULL COMMENT '更新时间',
                                   `creator` bigint NULL DEFAULT NULL COMMENT '创建者',
                                   `create_date` datetime NULL DEFAULT NULL COMMENT '创建时间',
                                   PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '设备信息' ROW_FORMAT = DYNAMIC;

SET FOREIGN_KEY_CHECKS = 1;
