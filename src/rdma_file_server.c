// rdma_file_server.c (fixed)
#include <rdma/rdma_cma.h>
#include <infiniband/verbs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <arpa/inet.h> // ntohll helper
#include <inttypes.h>

#define PORT "7471"
#define BUF_SIZE 4096

// helper for 64-bit ntoh
static inline uint64_t ntohll(uint64_t x) {
#if __BYTE_ORDER == __LITTLE_ENDIAN
    return (((uint64_t)ntohl(x & 0xFFFFFFFFULL)) << 32) | ntohl(x >> 32);
#else
    return x;
#endif
}

int main() {
    struct rdma_event_channel *ec = rdma_create_event_channel();
    struct rdma_cm_id *listen_id = NULL, *conn_id = NULL;
    struct rdma_addrinfo hints = {}, *res;
    struct ibv_pd *pd;
    struct ibv_cq *cq;
    struct ibv_mr *mr;
    char *buf = malloc(BUF_SIZE);
    if (!buf) { perror("malloc"); exit(1); }

    hints.ai_flags = RAI_PASSIVE;
    hints.ai_port_space = RDMA_PS_TCP;
    rdma_getaddrinfo(NULL, PORT, &hints, &res);

    rdma_create_id(ec, &listen_id, NULL, RDMA_PS_TCP);
    rdma_bind_addr(listen_id, res->ai_src_addr);
    rdma_listen(listen_id, 1);
    printf("[Server] Listening on port %s...\n", PORT);

    struct rdma_cm_event *event;
    rdma_get_cm_event(ec, &event);
    conn_id = event->id;
    rdma_ack_cm_event(event);

    pd = ibv_alloc_pd(conn_id->verbs);
    cq = ibv_create_cq(conn_id->verbs, 10, NULL, NULL, 0);

    struct ibv_qp_init_attr qp_attr = {
        .send_cq = cq, .recv_cq = cq, .qp_type = IBV_QPT_RC,
        .cap = {.max_send_wr = 10, .max_recv_wr = 10,
                .max_send_sge = 1, .max_recv_sge = 1}
    };
    rdma_create_qp(conn_id, pd, &qp_attr);

    mr = ibv_reg_mr(pd, buf, BUF_SIZE, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_WRITE);

    struct ibv_sge sge = {.addr=(uintptr_t)buf, .length=BUF_SIZE, .lkey=mr->lkey};
    struct ibv_recv_wr wr = {.wr_id=1, .sg_list=&sge, .num_sge=1};
    struct ibv_recv_wr *bad;

    // post initial recv (for header)
    if (ibv_post_recv(conn_id->qp, &wr, &bad)) { perror("ibv_post_recv"); exit(1); }

    rdma_accept(conn_id, NULL);
    printf("[Server] Connection accepted. Waiting for file...\n");

    struct ibv_wc wc;

    // 1) Wait for header (8 bytes)
    while (ibv_poll_cq(cq, 1, &wc) == 0);
    if (wc.status != IBV_WC_SUCCESS) { fprintf(stderr, "header recv failed\n"); exit(1); }
    uint64_t net_size;
    if (wc.byte_len < sizeof(net_size)) {
        fprintf(stderr, "header too small\n"); exit(1);
    }
    memcpy(&net_size, buf, sizeof(net_size));
    uint64_t file_size = ntohll(net_size);
    // repost recv for next data
    if (ibv_post_recv(conn_id->qp, &wr, &bad)) { perror("ibv_post_recv"); exit(1); }

    int fd = open("received_file.bin", O_CREAT | O_WRONLY | O_TRUNC, 0644);
    if (fd < 0) { perror("open"); exit(1); }

    uint64_t total = 0;
    while (total < file_size) {
        while (ibv_poll_cq(cq, 1, &wc) == 0);
        if (wc.status != IBV_WC_SUCCESS) { fprintf(stderr, "recv failed\n"); break; }
        size_t got = wc.byte_len; // exact length received
        if (got > 0) {
            ssize_t w = write(fd, buf, got); // write exact bytes
            if (w < 0) { perror("write"); break; }
            total += (uint64_t)w;
        }
        // repost for next chunk
        if (ibv_post_recv(conn_id->qp, &wr, &bad)) { perror("ibv_post_recv"); exit(1); }
    }

    printf("[Server] File saved to received_file.bin (%" PRIu64 " bytes)\n", total);
    close(fd);

    rdma_disconnect(conn_id);
    rdma_destroy_qp(conn_id);
    ibv_dereg_mr(mr);
    free(buf);
    rdma_destroy_id(conn_id);
    rdma_destroy_id(listen_id);
    rdma_destroy_event_channel(ec);
    return 0;
}