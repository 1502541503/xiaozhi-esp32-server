/*
 * @Author: plus666
 * @Date: 2025-08-14 16:51:00
 * @LastEditors: plus666
 * @LastEditTime: 2025-08-18 10:45:24
 * @FilePath: \xiaozhi-esp32-server\main\manager-web\src\apis\module\device.js
 */
import { getServiceUrl } from '../api';
import RequestService from '../httpRequest';

export default {
    // 已绑设备
    getAgentBindDevices(agentId, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/device/bind/${agentId}`)
            .method('GET')
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('获取设备列表失败:', err);
                RequestService.reAjaxFun(() => {
                    this.getAgentBindDevices(agentId, callback);
                });
            }).send();
    },
    // 解绑设备
    unbindDevice(device_id, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/device/unbind`)
            .method('POST')
            .data({ deviceId: device_id })
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('解绑设备失败:', err);
                RequestService.reAjaxFun(() => {
                    this.unbindDevice(device_id, callback);
                });
            }).send();
    },
    // 绑定设备
    bindDevice(agentId, deviceCode, remark, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/device/bind/${agentId}/${deviceCode}?remark=${remark}`)
            .method('POST')
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('绑定设备失败:', err);
                RequestService.reAjaxFun(() => {
                    this.bindDevice(agentId, deviceCode, remark, callback);
                });
            }).send();
    },
    // 批量添加设备
    bindBatchDevice(agentId, remark, file, callback) {
        const formData = new FormData();
        formData.append('file', file);
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/device/bind/batch?agentId=${agentId}&remark=${remark}`)
            .data(formData)
            .method('POST')
            .header({ 'Content-Type': 'multipart/form-data' })
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('绑定设备失败:', err);
                RequestService.reAjaxFun(() => {
                    this.bindBatchDevice(agentId, remark, file, callback);
                });
            }).send();
    },
    // 修改备注
    updateRemark(deviceCode, remark, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/device/updateRemark/${deviceCode}?remark=${remark}`)
            .method('POST')
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('修改备注失败:', err);
                RequestService.reAjaxFun(() => {
                    this.updateRemark(deviceCode, remark, callback);
                });
            }).send();
    },
    enableOtaUpgrade(id, status, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/device/enableOta/${id}/${status}`)
            .method('PUT')
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res)
            })
            .networkFail((err) => {
                console.error('更新OTA状态失败:', err)
                this.$message.error(err.msg || '更新OTA状态失败')
                RequestService.reAjaxFun(() => {
                    this.enableOtaUpgrade(id, status, callback)
                })
            }).send()
    },
}