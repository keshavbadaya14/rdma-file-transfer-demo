#include <rdma/rdma_cma.h>
#include <infiniband/verbs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define PORT "7471"
#define BUF_SIZE 4096

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <server_ip> <file_to_send>\n", argv[0]);
        return 1;
    }

    struct rdma_event_channel *ec = rdma_create_event_channel();
    struct rdma_cm_id *conn_id;
    struct rdma_addrinfo hints = {}, *res;
    struct ibv_pd *pd;
    struct ibv_cq *cq;
    struct ibv_mr *mr;
    char *buf = malloc(BUF_SIZE);

    hints.ai_port_space = RDMA_PS_TCP;
    rdma_getaddrinfo(argv[1], PORT, &hints, &res);
    rdma_create_id(ec, &conn_id, NULL, RDMA_PS_TCP);
    rdma_resolve_addr(conn_id, NULL, res->ai_dst_addr, 2000);

    struct rdma_cm_event *event;
    rdma_get_cm_event(ec, &event);
    rdma_ack_cm_event(event);

    rdma_resolve_route(conn_id, 2000);
    rdma_get_cm_event(ec, &event);
    rdma_ack_cm_event(event);

    pd = ibv_alloc_pd(conn_id->verbs);
    cq = ibv_create_cq(conn_id->verbs, 10, NULL, NULL, 0);

    struct ibv_qp_init_attr qp_attr = {
        .send_cq = cq, .recv_cq = cq, .qp_type = IBV_QPT_RC,
        .cap = {.max_send_wr = 10, .max_recv_wr = 10,
                .max_send_sge = 1, .max_recv_sge = 1}
    };
    rdma_create_qp(conn_id, pd, &qp_attr);

    mr = ibv_reg_mr(pd, buf, BUF_SIZE, IBV_ACCESS_LOCAL_WRITE);
    rdma_connect(conn_id, NULL);
    rdma_get_cm_event(ec, &event);
    rdma_ack_cm_event(event);

    printf("[Client] Connected to server. Sending file...\n");

    FILE *f = fopen(argv[2], "r");
    if (!f) { perror("fopen"); exit(1); }

    struct ibv_sge sge;
    struct ibv_send_wr wr = {.wr_id=1, .sg_list=&sge, .num_sge=1,
        .opcode=IBV_WR_SEND, .send_flags=IBV_SEND_SIGNALED};
    struct ibv_send_wr *bad;
    struct ibv_wc wc;

    while (fgets(buf, BUF_SIZE, f)) {
        sge.addr = (uintptr_t)buf; sge.length = strlen(buf); sge.lkey = mr->lkey;
        ibv_post_send(conn_id->qp, &wr, &bad);
        while (ibv_poll_cq(cq, 1, &wc) == 0);
    }
    fclose(f);

    strcpy(buf, "EOF");
    sge.addr = (uintptr_t)buf; sge.length = strlen(buf)+1; sge.lkey = mr->lkey;
    ibv_post_send(conn_id->qp, &wr, &bad);
    while (ibv_poll_cq(cq, 1, &wc) == 0);

    printf("[Client] File sent successfully.\n");

    rdma_disconnect(conn_id);
    rdma_destroy_qp(conn_id);
    ibv_dereg_mr(mr);
    free(buf);
    rdma_destroy_id(conn_id);
    rdma_destroy_event_channel(ec);
    return 0;
}
